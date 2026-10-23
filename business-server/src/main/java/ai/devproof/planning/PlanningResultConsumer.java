package ai.devproof.planning;

import ai.devproof.agentjob.AgentResultConsumer;
import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import ai.devproof.project.ProjectAccess;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class PlanningResultConsumer implements AgentResultConsumer {
    private final PlanningMapper data;
    private final RepositorySnapshotService repositories;
    private final PlanValidator validator;
    private final ProjectAccess access;
    public PlanningResultConsumer(PlanningMapper data,RepositorySnapshotService repositories,PlanValidator validator,ProjectAccess access) {
        this.data=data; this.repositories=repositories; this.validator=validator; this.access=access;
    }
    @Override public boolean supports(String kind) { return kind.equals("PLAN_DRAFT") || kind.equals("PLAN_REFINE"); }
    @Override public String schemaVersion() { return "planning-result-v1"; }
    @Override public void accept(Map<String,Object> task,Map<String,Object> candidates,List<UUID> evidenceRefs) {
        UUID projectId=(UUID)task.get("project_id"), actorId=(UUID)task.get("created_by"), runId=(UUID)task.get("planning_run_id");
        access.require(projectId,actorId,"SUBMITTER","ADMIN");
        Map<String,Object> run=data.runById(runId);
        if(run==null || !projectId.equals(run.get("project_id")))throw stale();
        Map<String,Object> revision=data.revisionById((UUID)run.get("idea_revision_id"));
        if(revision==null || data.lockIdea(projectId,(UUID)revision.get("idea_id"))==null)throw stale();
        if(!revision.get("id").equals(data.latestRevision((UUID)revision.get("idea_id")).get("id")))throw stale();
        Map<String,Object> input=data.inputById((UUID)run.get("snapshot_id"));
        if(input==null || !Json.hash((String)input.get("input_json")).equals(input.get("content_hash")))throw stale();
        Map<String,Object> repository=repositories.load(projectId,(UUID)input.get("repository_snapshot_id"));
        validator.validate(candidates,Json.object((String)repository.get("body_json")));
        if("CLARIFICATION".equals(candidates.get("kind"))) {
            for(Map<String,Object> question:PlanValidator.objects(candidates,"questions",30))
                data.question(UUID.randomUUID(),runId,(String)question.get("key"),(String)question.get("question"),(String)question.get("reason"));
        } else {
            String body=Json.write(candidates); UUID parent=null;
            Object previous=Json.object((String)input.get("input_json")).get("previousPlan");
            if(previous instanceof Map<?,?> previousPlan)parent=UUID.fromString((String)previousPlan.get("id"));
            data.plan(UUID.randomUUID(),(UUID)revision.get("id"),runId,data.nextPlanSequence((UUID)revision.get("id")),parent,body,Json.hash(body),actorId);
        }
        data.succeeded(runId);
    }
    private ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","规划输入已变更或引用不一致"); }
}
