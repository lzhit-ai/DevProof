package ai.devproof.question;

import ai.devproof.agentjob.AgentAssignments;
import ai.devproof.evidence.EvidenceMaterials;
import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EvidenceQuestions {
    public record Input(Map<String,Object> run,Map<String,Object> body) {}
    private static final Set<String> STATUSES=Set.of("CONFIRMED","PARTIALLY_SUPPORTED","CONFLICTING","INSUFFICIENT_EVIDENCE","INFERENCE_REQUIRES_CONFIRMATION");
    private final EvidenceQuestionStore data;
    private final EvidenceMaterials evidence;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final AgentAssignments assignments;
    private final CommandStore commands;
    private final BusinessAudit audit;
    public EvidenceQuestions(EvidenceQuestionStore data,EvidenceMaterials evidence,ProjectAccess access,BusinessOwnership owners,AgentAssignments assignments,CommandStore commands,BusinessAudit audit) {
        this.data=data; this.evidence=evidence; this.access=access; this.owners=owners; this.assignments=assignments; this.commands=commands; this.audit=audit;
    }
    @Transactional public CommandStore.Result ask(UUID snapshot,UUID actor,CommandStore.Context command,String question,List<UUID> refs) {
        var scope=data.snapshot(snapshot); UUID project=(UUID)scope.get("project_id"); access.require(project,actor); owners.requireJavaEvidenceQuestions();
        return commands.execute(command,202,()->{
            List<Map<String,Object>> selected=refs.stream().map(id->projection(evidence.citation(snapshot,id,actor))).toList();
            String raw=Json.canonical(Map.of("schemaVersion","evidence-question-input-v1","projectId",project.toString(),"snapshotId",snapshot.toString(),
                "snapshotHash",scope.get("snapshot_hash"),"question",question,"evidence",selected));
            UUID id=UUID.randomUUID(); data.create(id,project,snapshot,actor,raw);
            var manifest=assignments.manifest(actor,Set.of("evidence-question-agent"),Set.of("read_evidence_question_input"),null,Map.of(),Map.of("informationalOnly",true));
            List<String> allowed=new LinkedHashSet<>(refs).stream().map(UUID::toString).toList();
            UUID task=assignments.enqueueQuestion(project,actor,id,Map.of("kind","EVIDENCE_QUESTION","id",id.toString(),"contentHash",Json.hash(raw),"schemaVersion","evidence-question-input-v1"),allowed,manifest,command.correlationId());
            audit.append(project,actor,"EvidenceQuestionRun",id,"EVIDENCE_QUESTION_QUEUED",command.correlationId(),Map.of("snapshotId",snapshot.toString(),"inputHash",Json.hash(raw),"agentTaskId",task.toString()),null,null);
            return Map.of("id",id,"status","QUEUED","agent_task_id",task,"poll_url","/api/v1/agent-tasks/"+task,"result_url","/api/v1/input-snapshots/"+snapshot+"/questions/"+id,"informational_only",true);
        });
    }
    @Transactional public List<Map<String,Object>> list(UUID snapshot,UUID actor) {
        UUID project=(UUID)data.snapshot(snapshot).get("project_id"); String role=access.role(project,actor); return data.list(snapshot,project,actor,"ADMIN".equals(role));
    }
    @Transactional public Map<String,Object> get(UUID snapshot,UUID id,UUID actor) {
        UUID project=(UUID)data.snapshot(snapshot).get("project_id"); String role=access.role(project,actor); var row=data.get(snapshot,id,project);
        if(!actor.equals(row.get("created_by")) && !"ADMIN".equals(role))throw new ApiProblem(403,"AUTH_FORBIDDEN","问答内容只向发起者及项目管理员开放"); return EvidenceQuestionStore.view(row);
    }
    /** The caller holds the actual task lock and validates lease/fence before this read. */
    public Input input(Map<String,Object> task) {
        owners.requireJavaEvidenceQuestions();
        if(!"EVIDENCE_QUESTION".equals(task.get("task_kind")) || !(task.get("question_run_id") instanceof UUID id))throw stale();
        var run=data.lock(id); UUID project=(UUID)task.get("project_id"),actor=(UUID)task.get("created_by"); access.require(project,actor);
        var payload=Json.object((String)task.get("payload_json")); var ref=object(payload.get("inputSnapshotRef"));
        if(!project.equals(run.get("project_id")) || !actor.equals(run.get("created_by")) || !"RUNNING".equals(run.get("status"))
            || !"EVIDENCE_QUESTION".equals(ref.get("kind")) || !id.toString().equals(ref.get("id")) || !"evidence-question-input-v1".equals(ref.get("schemaVersion"))
            || !run.get("input_hash").equals(ref.get("contentHash")) || !Json.hash((String)run.get("input_json")).equals(run.get("input_hash")))throw stale();
        var body=Json.object((String)run.get("input_json")); UUID snapshot=(UUID)run.get("snapshot_id"); var scope=data.snapshot(snapshot);
        if(!project.equals(scope.get("project_id")) || !project.toString().equals(body.get("projectId")) || !snapshot.toString().equals(body.get("snapshotId"))
            || !scope.get("snapshot_hash").equals(body.get("snapshotHash")) || !"evidence-question-input-v1".equals(body.get("schemaVersion")))throw stale();
        Set<String> selected=new HashSet<>();
        for(Object value:evidenceList(body)) {
            var saved=object(value); UUID evidenceId=ApiInput.uuid(saved.get("evidenceId"));
            var current=projection(evidence.citation(snapshot,evidenceId,actor));
            if(!Json.canonical(current).equals(Json.canonical(saved)))throw stale(); selected.add(evidenceId.toString());
        }
        if(!(payload.get("allowedEvidenceIds") instanceof List<?> allowed) || !selected.equals(new HashSet<>(allowed)))throw stale();
        return new Input(run,body);
    }
    public void accept(Map<String,Object> task,Map<String,Object> result,List<UUID> refs) {
        var input=input(task);
        if(!result.keySet().equals(Set.of("answer","fact_status")))throw invalid();
        String answer=ApiInput.text(result,"answer",1,4000),status=ApiInput.text(result,"fact_status",1,64); if(!STATUSES.contains(status) || UnicodeText.strip(answer).isEmpty())throw invalid();
        List<Map<String,Object>> citations=new ArrayList<>(); Set<UUID> selected=new HashSet<>();
        for(Object value:evidenceList(input.body())) {
            var item=object(value); UUID id=ApiInput.uuid(item.get("evidenceId")); selected.add(id);
            citations.add(Map.of("evidenceId",id.toString(),"locator",item.get("locator"),"precision",item.get("precision")));
        }
        if(!selected.equals(new HashSet<>(refs)))throw new ApiProblem(422,"CITATION_INVALID","问答引用超出或遗漏本次冻结证据范围");
        Map<String,Object> output=Map.of("answer",answer,"fact_status",status,"citations",citations,"citation_scope","SUPPLIED_EVIDENCE","informational_only",true);
        UUID id=(UUID)input.run().get("id"); data.accepted(id,output);
        audit.append((UUID)task.get("project_id"),(UUID)task.get("created_by"),"EvidenceQuestionRun",id,"EVIDENCE_QUESTION_ANSWERED",id.toString(),Map.of("agentTaskId",task.get("id").toString(),"inputHash",input.run().get("input_hash"),"citationCount",citations.size()),null,null);
    }
    private static Map<String,Object> projection(Map<String,Object> row) {
        return Map.of("evidenceId",row.get("id").toString(),"sourceType",row.get("source_type"),"evidenceKind",row.get("evidence_kind"),"excerpt",row.get("excerpt_safe"),"locator",row.get("locator"),"precision",row.get("locator_precision"));
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object raw) { if(!(raw instanceof Map<?,?>))throw invalid(); return (Map<String,Object>)raw; }
    private static List<?> evidenceList(Map<String,Object> body) { if(!(body.get("evidence") instanceof List<?> list) || list.isEmpty() || list.size()>20)throw invalid(); return list; }
    private static ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","问答输入或当前授权证据范围已变化"); }
    private static ApiProblem invalid() { return new ApiProblem(422,"MODEL_SCHEMA_INVALID","问答内容不符合输入或结果契约"); }
}
