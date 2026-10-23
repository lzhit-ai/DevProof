package ai.devproof.verification;

import ai.devproof.agentjob.AgentTaskService;
import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class VerificationToolScope {
    private final VerificationExecutionMapper data;
    private final AgentTaskService tasks;
    public VerificationToolScope(VerificationExecutionMapper data,AgentTaskService tasks) { this.data=data; this.tasks=tasks; }
    public void revalidate(Map<String,Object> payload) {
        tasks.toolPayload(new AgentTaskService.Context(UUID.fromString((String)payload.get("taskId")),UUID.fromString((String)payload.get("attemptId")),((Number)payload.get("fencingToken")).longValue(),(String)payload.get("workerId")));
    }
    @SuppressWarnings("unchecked") public Map<String,Object> require(Map<String,Object> payload) {
        Map<String,Object> ref=(Map<String,Object>)payload.get("businessRef"), input=(Map<String,Object>)payload.get("inputSnapshotRef");
        if(!"ANALYSIS_RUN".equals(ref.get("kind")) || !"VERIFICATION".equals(input.get("kind")))throw stale();
        Map<String,Object> row=data.run(UUID.fromString((String)ref.get("id")));
        if(row==null || !"JAVA".equals(row.get("executor_owner")) || !row.get("project_id").toString().equals(payload.get("projectId")) || !row.get("snapshot_id").toString().equals(input.get("id")) || !row.get("snapshot_hash").equals(input.get("contentHash")))throw stale();
        Map<String,Object> manifest=(Map<String,Object>)payload.get("agentManifest"), configuration=(Map<String,Object>)manifest.get("businessConfigurationRef"), frozen=data.orchestrationJson((UUID)row.get("id"));
        if(configuration==null || frozen==null || !frozen.get("id").toString().equals(configuration.get("id")) || !frozen.get("content_hash").equals(configuration.get("contentHash")))throw stale();
        OrchestrationBodies.raw(frozen);
        return row;
    }
    @SuppressWarnings("unchecked") public int limit(Map<String,Object> payload,String key) {
        Map<String,Object> manifest=(Map<String,Object>)payload.get("agentManifest"), values=(Map<String,Object>)manifest.get("executionConfiguration");
        if(!(values.get(key) instanceof Number number) || number.intValue()<1)throw stale(); return number.intValue();
    }
    public List<Map<String,Object>> nodes(UUID run) { return VerificationMaterials.objects(OrchestrationBodies.body(data.orchestrationJson(run)).get("nodes")); }
    private ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","工具不属于当前冻结核验任务或编排已改变"); }
}
