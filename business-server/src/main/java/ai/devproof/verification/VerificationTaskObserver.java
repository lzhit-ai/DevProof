package ai.devproof.verification;

import ai.devproof.agentjob.AgentTaskObserver;
import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class VerificationTaskObserver implements AgentTaskObserver {
    private static final Map<String,String> OPERATIONS=Map.of("delivery-review-agent","CODE_REVIEW","finding-challenge-agent","CODE_REVIEW_CHALLENGE","evidence-link-agent","LINK_PROPOSAL","custom-evidence-agent","CUSTOM_AGENT");
    private static final Set<String> STAGES=Set.of("review_code","challenge_code_findings","propose_model_links","supplement_context","run_custom_agents");
    private final BusinessOwnership owners;
    private final VerificationExecutionMapper data;
    private final InputSnapshotMapper inputs;
    private final JdbcTemplate jdbc;
    public VerificationTaskObserver(BusinessOwnership owners,VerificationExecutionMapper data,InputSnapshotMapper inputs,JdbcTemplate jdbc) {
        this.owners=owners; this.data=data; this.inputs=inputs; this.jdbc=jdbc;
    }
    public boolean supports(String kind) { return "DELIVERY_VERIFY".equals(kind); }
    public void status(Map<String,Object> task,String status,String code) {
        owners.requireJavaVerification(); UUID id=(UUID)task.get("analysis_run_id");
        Map<String,Object> run=data.run(id); if(run==null || !"JAVA".equals(run.get("executor_owner")))throw invalid();
        data.status(id,status);
        if("RUNNING".equals(status))jdbc.update("UPDATE node_attempts SET status='EXPIRED',error_code='LEASE_EXPIRED',finished_at=clock_timestamp() WHERE analysis_run_id=? AND status='RUNNING' AND attempt_no<?",id,task.get("attempt_no"));
        if("QUEUED".equals(status))jdbc.update("UPDATE node_attempts SET status='FAILED',error_code=?,finished_at=clock_timestamp() WHERE analysis_run_id=? AND status='RUNNING'",code,id);
        UUID cycle=(UUID)run.get("cycle_id"); inputs.lockCycle(cycle);
        if("CANCELLED".equals(status))data.cancelled(id);
        if(Set.of("FAILED","CANCELLED").contains(status)) {
            jdbc.update("UPDATE node_attempts SET status=?,error_code=?,finished_at=clock_timestamp() WHERE analysis_run_id=? AND status='RUNNING'",status,code,id);
            jdbc.update("UPDATE verification_cycles SET business_status=CASE WHEN ?='CANCELLED' THEN 'DRAFT' ELSE 'NEEDS_EVIDENCE' END,updated_at=clock_timestamp() WHERE id=? AND active_run_id=? AND business_status='ANALYZING'",status,cycle,id);
        }
        Map<String,Object> payload=new LinkedHashMap<>(); payload.put("attempt",task.get("attempt_no")); if(code!=null)payload.put("error",code);
        data.event(UUID.randomUUID(),id,null,"JOB_EXECUTION",status,id.toString(),Json.write(payload));
    }
    @SuppressWarnings("unchecked")
    public void event(Map<String,Object> task,Map<String,Object> event) {
        owners.requireJavaVerification(); UUID run=(UUID)task.get("analysis_run_id");
        String type=Objects.toString(event.get("eventType"),"");
        if(!(event.get("payloadRedacted") instanceof Map<?,?> raw))throw invalid();
        Map<String,Object> payload=(Map<String,Object>)raw; String stage=Objects.toString(payload.get("stage"),"");
        Map<String,Object> frozen=Json.object((String)task.get("payload_json"));
        if(type.startsWith("STAGE_")) {
            if(!STAGES.contains(stage))throw invalid();
            String status=switch(type) { case "STAGE_STARTED"->"RUNNING"; case "STAGE_COMPLETED"->"SUCCEEDED"; case "STAGE_FAILED"->"FAILED"; case "STAGE_SKIPPED"->"SKIPPED"; default->throw invalid(); };
            String code=payload.get("errorCode") instanceof String value?value:null;
            jdbc.update("""
                INSERT INTO node_attempts(id,analysis_run_id,node_id,attempt_no,status,error_code,finished_at)
                VALUES(?,?,?,?,?,?,CASE WHEN ?='RUNNING' THEN NULL ELSE clock_timestamp() END)
                ON CONFLICT(analysis_run_id,node_id,attempt_no) DO UPDATE SET status=excluded.status,error_code=excluded.error_code,finished_at=excluded.finished_at
                """,UUID.randomUUID(),run,stage,task.get("attempt_no"),status,code,status);
            data.event(UUID.randomUUID(),run,stage,"NODE",status,Objects.toString(frozen.get("correlationId"),run.toString()),Json.write(payload));
        } else {
            data.event(UUID.randomUUID(),run,STAGES.contains(stage)?stage:null,type.length()<=64?type:"AGENT_EVENT","RECORDED",Objects.toString(frozen.get("correlationId"),run.toString()),Json.write(payload));
        }
        if(Set.of("MODEL_TURN_COMPLETED","MODEL_TURN_FAILED").contains(type)) {
            String agent=Objects.toString(payload.get("agentKey"),""), operation=OPERATIONS.get(agent);
            Map<String,Object> manifest=(Map<String,Object>)frozen.get("agentManifest"), model=(Map<String,Object>)manifest.get("modelConfiguration");
            if(operation==null || ((List<Map<String,Object>>)manifest.get("agents")).stream().noneMatch(item->agent.equals(item.get("key"))))throw invalid();
            Object latency=payload.get("latencyMs");
            if(!(latency instanceof Number time) || time.longValue()<0 || time.longValue()>Integer.MAX_VALUE)throw invalid();
            String error=payload.get("errorCode") instanceof String value?value:null;
            jdbc.update("""
                INSERT INTO model_calls(id,run_id,agent_task_attempt_id,provider,model,operation,prompt_version,schema_version,allowed_evidence_ids,status,latency_ms,attempts,error_code,usage)
                VALUES(?,?,?,?,?,?,'verification-agents-v1','verification-result-v1',CAST(? AS jsonb),?,?,1,?,CAST(? AS jsonb))
                """,UUID.randomUUID(),run,task.get("current_attempt_id"),model.get("provider"),model.get("model"),operation,Json.write(frozen.get("allowedEvidenceIds")),
                type.equals("MODEL_TURN_COMPLETED")?"SUCCEEDED":"FAILED",time.intValue(),error,Json.write(payload.getOrDefault("usage",Map.of())));
        }
        if("MODEL_OUTPUT_REJECTED".equals(type)) {
            String operation=OPERATIONS.get(Objects.toString(payload.get("agentKey"),"")); if(operation==null)throw invalid();
            jdbc.update("UPDATE model_calls SET status='FAILED',error_code='MODEL_SCHEMA_INVALID' WHERE id=(SELECT id FROM model_calls WHERE agent_task_attempt_id=? AND operation=? ORDER BY created_at DESC,id DESC LIMIT 1)",task.get("current_attempt_id"),operation);
        }
    }
    private ApiProblem invalid() { return new ApiProblem(422,"EVENT_INVALID","核验事件不符合任务冻结范围"); }
}
