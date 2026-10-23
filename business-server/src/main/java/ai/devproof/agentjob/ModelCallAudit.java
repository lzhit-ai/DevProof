package ai.devproof.agentjob;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Domain handlers choose the registered operation; only real Worker turn events are recorded. */
@Component
public class ModelCallAudit {
    private final JdbcTemplate jdbc;
    public ModelCallAudit(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    @SuppressWarnings("unchecked") public void record(Map<String,Object> task,Map<String,Object> event,String agent,String operation,String promptVersion,String schema) {
        String type=Objects.toString(event.get("eventType"),"");
        if(!Set.of("MODEL_TURN_COMPLETED","MODEL_TURN_FAILED","MODEL_OUTPUT_REJECTED").contains(type))return;
        if(!(event.get("payloadRedacted") instanceof Map<?,?> raw) || !agent.equals(raw.get("agentKey")))throw new ApiProblem(422,"EVENT_INVALID","模型事件不属于本任务注册的 Agent");
        var payload=Json.object((String)task.get("payload_json")); var manifest=(Map<String,Object>)payload.get("agentManifest");
        if(((List<Map<String,Object>>)manifest.get("agents")).stream().noneMatch(value->agent.equals(value.get("key"))))throw new ApiProblem(422,"EVENT_INVALID","模型事件未获任务授权");
        if("MODEL_OUTPUT_REJECTED".equals(type)) {
            jdbc.update("UPDATE model_calls SET status='FAILED',error_code='MODEL_SCHEMA_INVALID' WHERE id=(SELECT id FROM model_calls WHERE agent_task_attempt_id=? AND operation=? ORDER BY created_at DESC,id DESC LIMIT 1)",task.get("current_attempt_id"),operation); return;
        }
        if(!(raw.get("latencyMs") instanceof Number latency) || latency.longValue()<0 || latency.longValue()>Integer.MAX_VALUE || latency.doubleValue()!=latency.longValue())throw new ApiProblem(422,"EVENT_INVALID","模型调用时长不符合约束");
        var model=(Map<String,Object>)manifest.get("modelConfiguration");
        jdbc.update("""
            INSERT INTO model_calls(id,agent_task_attempt_id,provider,model,operation,prompt_version,schema_version,allowed_evidence_ids,status,latency_ms,attempts,error_code,usage)
            VALUES(?,?,?,?,?,?,?,CAST(? AS jsonb),?,?,1,?,CAST(? AS jsonb))
            """,UUID.randomUUID(),task.get("current_attempt_id"),model.get("provider"),model.get("model"),operation,promptVersion,schema,
            Json.write(payload.get("allowedEvidenceIds")),type.equals("MODEL_TURN_COMPLETED")?"SUCCEEDED":"FAILED",latency.intValue(),raw.get("errorCode"),Json.write(raw.containsKey("usage")?raw.get("usage"):Map.of()));
    }
}
