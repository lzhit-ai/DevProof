package ai.devproof.delivery;

import ai.devproof.agentjob.AgentAssignments;
import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeliveryClaims {
    public record Confirmation(UUID id,String text) {}
    private record Selected(UUID id,String key,String text,boolean existing) {}
    public record Input(Map<String,Object> run,Map<String,Object> body,Map<String,Object> scope) {}
    private final DeliveryClaimsStore data;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final ControlledArtifacts artifacts;
    private final AgentAssignments assignments;
    public DeliveryClaims(DeliveryClaimsStore data,ProjectAccess access,BusinessOwnership owners,CommandStore commands,
            BusinessAudit audit,ControlledArtifacts artifacts,AgentAssignments assignments) {
        this.data=data; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit; this.artifacts=artifacts; this.assignments=assignments;
    }
    @Transactional public List<Map<String,Object>> list(UUID project,UUID task,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); return data.views((UUID)data.scope(project,task).get("cycle_id"));
    }
    @Transactional public List<Map<String,Object>> runs(UUID project,UUID task,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); return data.runs((UUID)data.scope(project,task).get("cycle_id"));
    }
    @Transactional public CommandStore.Result propose(UUID project,UUID task,UUID actor,CommandStore.Context command,List<UUID> sources) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaDeliveryClaims(); var scope=data.scope(project,task);
        return commands.execute(command,202,()->{
            data.editable(scope,true); UUID cycle=(UUID)scope.get("cycle_id");
            if(data.active(cycle))throw new ApiProblem(409,"CLAIM_PROPOSAL_ACTIVE","本轮已有提取任务排队或执行中");
            var pr=data.pullRequest(scope); List<Map<String,Object>> documents=new ArrayList<>(),manifestDocuments=new ArrayList<>();
            for(UUID id:sources) {
                var source=data.source(project,id);
                String uri=(String)(source.get("extracted_artifact_uri")==null?source.get("artifact_uri"):source.get("extracted_artifact_uri"));
                String text=artifacts.text(uri,268435456,(String)source.get("normalized_text_hash")),excerpt=prefix(text,4000);
                Map<String,Object> document=new LinkedHashMap<>(); document.put("sourceRevisionId",id.toString()); document.put("name",source.get("logical_name"));
                document.put("contentHash",source.get("content_hash")); document.put("extractedTextHash",Json.hash(text));
                document.put("excerpt",excerpt); document.put("excerptHash",Json.hash(excerpt)); documents.add(document);
                manifestDocuments.add(Map.of("sourceRevisionId",id.toString(),"name",source.get("logical_name"),"contentHash",source.get("content_hash")));
            }
            Map<String,Object> pullRequest=new LinkedHashMap<>(); pullRequest.put("deliveryItemId",pr.get("item_id").toString());
            pullRequest.put("revisionId",pr.get("revision_id").toString()); pullRequest.put("contentHash",pr.get("content_hash"));
            pullRequest.put("title",pr.get("title")); pullRequest.put("body",pr.get("body")); pullRequest.put("webUrl",pr.get("web_url"));
            Map<String,Object> manifest=Map.of("pullRequest",pullRequest,"documents",manifestDocuments);
            String body=Json.canonical(Map.of("schemaVersion","delivery-claim-input-v1","projectId",project.toString(),"taskId",task.toString(),"cycleId",cycle.toString(),"sourceManifest",manifest,"documents",documents));
            UUID run=UUID.randomUUID(); data.create(run,project,task,cycle,actor,body,manifest);
            var agentManifest=assignments.manifest(actor,Set.of("delivery-claim-proposer"),Set.of("read_claim_proposal_input"),null,Map.of(),Map.of("documentExcerptChars",4000));
            UUID agentTask=assignments.enqueueClaim(project,actor,run,Map.of("kind","CLAIM_PROPOSAL","id",run.toString(),"contentHash",Json.hash(body),"schemaVersion","delivery-claim-input-v1"),agentManifest,command.correlationId());
            audit.append(project,actor,"DeliveryClaimProposalRun",run,"DELIVERY_CLAIM_PROPOSAL_QUEUED",command.correlationId(),Map.of("cycleId",cycle.toString(),"agentTaskId",agentTask.toString(),"inputHash",Json.hash(body)),null,null);
            return Map.of("run_id",run,"agent_task_id",agentTask,"status","QUEUED","poll_url","/api/v1/agent-tasks/"+agentTask);
        });
    }
    @Transactional public CommandStore.Result confirm(UUID project,UUID task,UUID actor,CommandStore.Context command,List<Confirmation> claims) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaDeliveryClaims(); var scope=data.scope(project,task);
        return commands.execute(command,200,()->{
            data.editable(scope,false); UUID cycle=(UUID)scope.get("cycle_id");
            var existing=data.drafts(cycle,true); Map<UUID,Map<String,Object>> byId=new HashMap<>(); Map<String,Map<String,Object>> byKey=new HashMap<>();
            for(var row:existing) { byId.put((UUID)row.get("id"),row); byKey.put((String)row.get("claim_key"),row); }
            Set<UUID> selectedIds=new HashSet<>(); List<Selected> selected=new ArrayList<>(); int index=0;
            for(var claim:claims) {
                String text=UnicodeText.strip(claim.text()); if(text.codePointCount(0,text.length())<3)throw ApiInput.invalid();
                String key="HUMAN-"+(++index)+"-"+Json.hash(text).substring(7,19);
                Map<String,Object> row=claim.id()==null?byKey.get(key):byId.get(claim.id());
                if(claim.id()!=null && row==null)throw new ApiProblem(422,"INPUT_INVALID","主张不存在或不属于本轮");
                UUID id=row==null?UUID.randomUUID():(UUID)row.get("id"); if(!selectedIds.add(id))throw new ApiProblem(422,"INPUT_INVALID","同一主张不能重复确认");
                selected.add(new Selected(id,row==null?key:(String)row.get("claim_key"),text,row!=null));
            }
            data.discard(cycle,"CONFIRMED");
            for(var claim:selected)data.confirm(claim.id(),cycle,claim.key(),claim.text(),actor,claim.existing());
            audit.append(project,actor,"VerificationCycle",cycle,"DELIVERY_CLAIMS_CONFIRMED",command.correlationId(),Map.of("count",selected.size()),null,null);
            return Map.of("claims",data.views(cycle).stream().filter(row->selectedIds.contains(row.get("id"))).toList());
        });
    }
    /** Called with the actual task row locked by the task center, never a model-selected ID. */
    public Input input(Map<String,Object> task) {
        owners.requireJavaDeliveryClaims();
        if(!"DELIVERY_CLAIM_PROPOSE".equals(task.get("task_kind")) || !(task.get("claim_proposal_run_id") instanceof UUID runId))throw stale();
        UUID project=(UUID)task.get("project_id"),actor=(UUID)task.get("created_by"); access.require(project,actor,"SUBMITTER","ADMIN");
        var run=data.run(runId); var payload=Json.object((String)task.get("payload_json")); var ref=object(payload.get("inputSnapshotRef"));
        if(!project.equals(run.get("project_id")) || !actor.equals(run.get("created_by")) || !"RUNNING".equals(run.get("status"))
            || !"CLAIM_PROPOSAL".equals(ref.get("kind")) || !runId.toString().equals(ref.get("id")) || !"delivery-claim-input-v1".equals(ref.get("schemaVersion"))
            || !run.get("input_hash").equals(ref.get("contentHash")) || !Json.hash((String)run.get("input_json")).equals(run.get("input_hash")))throw stale();
        var body=Json.object((String)run.get("input_json")); var scope=data.scope(project,(UUID)run.get("task_id"));
        if(!run.get("cycle_id").equals(scope.get("cycle_id")) || !project.toString().equals(body.get("projectId"))
            || !run.get("task_id").toString().equals(body.get("taskId")) || !run.get("cycle_id").toString().equals(body.get("cycleId"))
            || !"delivery-claim-input-v1".equals(body.get("schemaVersion")))throw stale();
        data.editable(scope,true);
        var manifest=object(body.get("sourceManifest")); var pr=object(manifest.get("pullRequest"));
        if(scope.get("delivery_item_id")==null || !scope.get("delivery_item_id").toString().equals(pr.get("deliveryItemId")))throw stale();
        for(Object value:list(body.get("documents"),20)) {
            var document=object(value); var source=data.source(project,ApiInput.uuid(document.get("sourceRevisionId")));
            if(!source.get("content_hash").equals(document.get("contentHash")) || source.get("normalized_text_hash")!=null && !source.get("normalized_text_hash").equals(document.get("extractedTextHash"))
                || !Json.hash(ApiInput.text(document,"excerpt",0,4000)).equals(document.get("excerptHash")))throw stale();
        }
        return new Input(run,body,scope);
    }
    public void accept(Map<String,Object> task,Map<String,Object> result,List<UUID> evidence) {
        if(!evidence.isEmpty() || !result.keySet().equals(Set.of("claims")))throw invalidResult();
        var input=input(task); UUID cycle=(UUID)input.run().get("cycle_id"),run=(UUID)input.run().get("id"),project=(UUID)task.get("project_id"),actor=(UUID)task.get("created_by");
        var claims=list(result.get("claims"),12); List<Map<String,String>> validated=new ArrayList<>();
        for(Object value:claims) {
            var candidate=object(value); if(!candidate.keySet().equals(Set.of("text","rationale")))throw invalidResult();
            String raw=ApiInput.text(candidate,"text",3,2000),text=UnicodeText.strip(raw),rationale=UnicodeText.strip(ApiInput.text(candidate,"rationale",1,2000));
            if(text.codePointCount(0,text.length())<3 || rationale.isEmpty())throw invalidResult();
            validated.add(Map.of("raw",raw,"text",text,"rationale",rationale));
        }
        Map<String,Object> manifest=new LinkedHashMap<>(object(input.body().get("sourceManifest"))); manifest.put("proposalRunId",run.toString()); manifest.put("inputHash",input.run().get("input_hash"));
        data.discard(cycle,"CANDIDATE"); int index=0;
        for(var claim:validated)data.candidate(cycle,"MODEL-"+(++index)+"-"+Json.hash(claim.get("raw")).substring(7,19),claim.get("text"),claim.get("rationale"),manifest,actor);
        data.status(run,"SUCCEEDED",null);
        audit.append(project,actor,"VerificationCycle",cycle,"DELIVERY_CLAIM_CANDIDATES_PROPOSED",run.toString(),Map.of("count",validated.size(),"proposalRunId",run.toString(),"agentTaskId",task.get("id").toString(),"inputHash",input.run().get("input_hash")),null,null);
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object value) { if(!(value instanceof Map<?,?>))throw invalidResult(); return (Map<String,Object>)value; }
    private static List<?> list(Object value,int max) { if(!(value instanceof List<?> values) || values.size()>max)throw invalidResult(); return values; }
    private static String prefix(String text,int max) { return text.codePointCount(0,text.length())<=max?text:text.substring(0,text.offsetByCodePoints(0,max)); }
    private static ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","主张提取输入或当前任务范围已变化"); }
    private static ApiProblem invalidResult() { return new ApiProblem(422,"MODEL_SCHEMA_INVALID","主张候选不符合冻结输入和结果契约"); }
}
