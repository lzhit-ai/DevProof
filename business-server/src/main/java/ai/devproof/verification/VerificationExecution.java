package ai.devproof.verification;

import ai.devproof.agentjob.*;
import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.retrieval.EmbeddingProfile;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Creates one frozen analysis and its executable task in the same business transaction. */
@Service
public class VerificationExecution {
    private final VerificationExecutionMapper data;
    private final InputSnapshotMapper inputs;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final VerificationOrchestration orchestration;
    private final VerificationMaterials materials;
    private final AgentAssignments assignments;
    private final AgentTaskService tasks;
    private final String embedding;
    private final Map<String,Object> limits;
    public VerificationExecution(VerificationExecutionMapper data,InputSnapshotMapper inputs,ProjectAccess access,BusinessOwnership owners,
            CommandStore commands,VerificationOrchestration orchestration,VerificationMaterials materials,AgentAssignments assignments,
            AgentTaskService tasks,EmbeddingProfile documentEmbedding,
            @Value("${CODE_REVIEW_INPUT_CHAR_BUDGET:96000}") int reviewBudget,@Value("${CODE_REVIEW_CHALLENGE_INPUT_CHAR_BUDGET:64000}") int challengeBudget,
            @Value("${CODE_REVIEW_CHALLENGE_MAX_FINDINGS:30}") int maxFindings,@Value("${CODE_REVIEW_CONTEXT_MAX_SUPPLEMENT_REQUESTS:5}") int supplementRequests,
            @Value("${CODE_REVIEW_CONTEXT_MAX_FILE_BYTES:262144}") int contextFileBytes,@Value("${CODE_REVIEW_CONTEXT_MAX_TOTAL_BYTES:1048576}") int contextTotalBytes,
            @Value("${AGENT_TOOL_TIMEOUT_SECONDS:10}") int toolTimeout,@Value("${AGENT_TOOL_RESPONSE_LIMIT_BYTES:262144}") int toolBytes) {
        this.data=data; this.inputs=inputs; this.access=access; this.owners=owners; this.commands=commands;
        this.orchestration=orchestration; this.materials=materials; this.assignments=assignments; this.tasks=tasks; this.embedding=(String)documentEmbedding.body().get("model");
        if(reviewBudget<8000 || reviewBudget>400000 || challengeBudget<8000 || challengeBudget>400000 || maxFindings<1 || maxFindings>100 || supplementRequests<1 || supplementRequests>20)throw new IllegalArgumentException("Invalid verification input budgets");
        if(contextFileBytes<4096 || contextFileBytes>2097152 || contextTotalBytes<65536 || contextTotalBytes>8388608 || toolTimeout<1 || toolTimeout>30 || toolBytes<4096 || toolBytes>1048576)throw new IllegalArgumentException("Invalid verification tool budgets");
        limits=Map.of("reviewInputCharBudget",reviewBudget,"challengeInputCharBudget",challengeBudget,"challengeMaxFindings",maxFindings,"contextMaxSupplementRequests",supplementRequests,
            "contextMaxFileBytes",contextFileBytes,"contextMaxTotalBytes",contextTotalBytes,"toolTimeoutSeconds",toolTimeout,"toolResponseLimitBytes",toolBytes,
            "documentEmbeddingConfiguration",documentEmbedding.body());
    }
    @Transactional
    public CommandStore.Result start(UUID snapshot,UUID actor,CommandStore.Context command) {
        Map<String,Object> scope=data.snapshotScope(snapshot);
        if(scope==null)throw missing();
        UUID project=(UUID)scope.get("project_id"), cycle=(UUID)scope.get("cycle_id");
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaVerification();
        return commands.execute(command,202,()-> {
            inputs.lockCycle(cycle); Map<String,Object> current=data.snapshotScope(snapshot);
            if(!"FORMAL".equals(current.get("purpose")))throw state("只有正式输入快照可以启动分析");
            if(!"DELIVERY_VERIFICATION".equals(current.get("assessment_profile")))throw new ApiProblem(409,"ASSESSMENT_PROFILE_NOT_ENABLED","该核验配置尚未交接 Java 执行");
            if(!Set.of("DRAFT","NEEDS_EVIDENCE","NEEDS_CONFIRMATION").contains(current.get("business_status")))throw state("当前轮次不能启动新的分析运行");
            if(data.frozenClaims(snapshot).isEmpty())throw new ApiProblem(409,"CLAIMS_NOT_CONFIRMED","正式快照缺少已确认的交付主张");
            Map<String,Object> git=data.git(snapshot);
            if(git==null || git.get("diff_artifact_id")==null || git.get("code_change_artifact_id")==null)throw new ApiProblem(409,"GIT_ARTIFACT_MISSING","交付核验缺少可回放 Git 制品");
            Map<String,Object> body=inputs.body(snapshot);
            if(body!=null && (!Json.hash((String)body.get("body_json")).equals(current.get("snapshot_hash")) || !Objects.equals(body.get("content_hash"),current.get("snapshot_hash"))))
                throw new ApiProblem(409,"INPUT_STALE","冻结输入正文摘要不一致");
            if("v2".equals(current.get("policy_version")) && body==null)throw new ApiProblem(409,"INPUT_STALE","冻结输入正文缺失");
            VerificationOrchestration.Frozen frozen=orchestration.load((UUID)current.get("task_id"),project,actor);
            UUID configuration=UUID.randomUUID(); Map<String,String> prompts=new LinkedHashMap<>();
            for(Map<String,Object> node:frozen.nodes())if(Boolean.TRUE.equals(node.get("enabled")) && !VerificationOrchestration.BUILT_IN.contains(node.get("capabilityKey")))
                prompts.put((String)node.get("capabilityKey"),(String)node.get("promptTemplate"));
            Map<String,Object> manifest=assignments.manifest(actor,Set.of("delivery-review-agent","finding-challenge-agent","evidence-link-agent","custom-evidence-agent"),
                Set.of("read_delivery_input","read_context_candidate","record_context_supplement","query_registered_tool","search_frozen_documents"),
                Map.of("kind","ORCHESTRATION","id",configuration.toString(),"contentHash",frozen.hash(),"schemaVersion","orchestration-v1"),prompts,limits);
            Map<String,Object> plan=data.plan(snapshot), config=new LinkedHashMap<>();
            config.put("workflow","delivery-agent-v3"); config.put("rules",VerificationRules.VERSION); config.put("schema","verification-result-v1");
            config.put("model",manifest.get("modelConfiguration")); config.put("modelConfigRef",manifest.get("modelConfigRef")); config.put("embeddingModel",embedding); config.put("orchestrationHash",frozen.hash());
            config.put("agents",manifest.get("agents")); config.put("tools",manifest.get("tools")); config.put("promptVersions",manifest.get("promptVersions"));
            config.put("executionConfiguration",limits);
            if(plan!=null)config.put("plan",Map.of("id",plan.get("plan_version_id").toString(),"contentHash",plan.get("plan_content_hash"),"selectionHash",plan.get("selection_hash")));
            String hash=Json.hash(Json.write(config)); UUID active=data.active(snapshot,hash);
            if(active!=null)return response(data.run(active));
            UUID run=UUID.randomUUID();
            data.createRun(run,snapshot,hash,Json.hash(Json.write(Map.of("configuration",config,"snapshot",current.get("snapshot_hash")))),"run-"+run,
                plan==null?null:(UUID)plan.get("plan_version_id"),plan==null?null:(String)plan.get("selection_hash"));
            data.manifest(UUID.randomUUID(),run,(String)((Map<?,?>)manifest.get("modelConfiguration")).get("model"),embedding);
            orchestration.freeze(run,configuration,frozen); materials.prepare(run,current);
            List<String> evidence=data.evidence(snapshot).stream().map(row->row.get("id").toString()).toList();
            assignments.enqueue(project,actor,run,null,"DELIVERY_VERIFY",
                Map.of("kind","VERIFICATION","id",snapshot.toString(),"contentHash",current.get("snapshot_hash"),"schemaVersion",body==null?"verification-input-v1":"verification-input-v2"),
                plan==null?null:Map.of("id",plan.get("plan_version_id").toString(),"contentHash",plan.get("plan_content_hash")),
                List.of(Map.of("repositoryId",git.get("repository_id").toString(),"targetSha",git.get("target_sha"))),evidence,manifest,command.correlationId());
            data.cycle(cycle,run,"ANALYZING");
            data.audit(UUID.randomUUID(),project,actor,run,"ANALYSIS_RUN_QUEUED",command.correlationId(),Json.write(Map.of("snapshotHash",current.get("snapshot_hash"),"orchestrationHash",frozen.hash(),"executorOwner","JAVA")));
            return response(data.run(run));
        });
    }
    @Transactional
    public Map<String,Object> cancel(UUID id,UUID actor) {
        Map<String,Object> run=data.run(id); if(run==null)throw missing();
        access.require((UUID)run.get("project_id"),actor,"SUBMITTER","ADMIN"); owners.requireJavaVerification();
        if(!"JAVA".equals(run.get("executor_owner")))throw state("该运行未由 Java 任务中心执行");
        if(!Set.of("QUEUED","RUNNING").contains(run.get("run_status")))throw state("当前运行不可取消");
        UUID task=data.agentTask(id); if(task==null)throw state("运行缺少执行任务");
        tasks.cancel(task,actor); return response(data.run(id));
    }
    static Map<String,Object> response(Map<String,Object> run) {
        return Map.of("id",run.get("id").toString(),"snapshot_id",run.get("snapshot_id").toString(),"assessment_profile",run.get("assessment_profile"),"run_status",run.get("run_status"),"poll_url","/api/v1/analysis-runs/"+run.get("id"));
    }
    private ApiProblem missing() { return new ApiProblem(404,"RESOURCE_NOT_FOUND","分析运行或输入快照不存在"); }
    private ApiProblem state(String message) { return new ApiProblem(409,"STATE_CONFLICT",message); }
}
