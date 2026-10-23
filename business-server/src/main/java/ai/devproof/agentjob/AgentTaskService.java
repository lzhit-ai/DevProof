package ai.devproof.agentjob;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import ai.devproof.project.ProjectAccess;
import ai.devproof.modelsettings.UserModelSettings;
import java.sql.Timestamp;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AgentTaskService {
    private static final Set<String> RETRYABLE = Set.of("MODEL_UNAVAILABLE", "MODEL_RATE_LIMITED", "TOOL_UNAVAILABLE", "NETWORK_ERROR", "WORKER_INTERRUPTED");
    private final AgentTaskMapper tasks;
    private final List<AgentResultConsumer> consumers;
    private final List<AgentTaskObserver> observers;
    private final ProjectAccess access;
    private final UserModelSettings models;
    private final int leaseSeconds;
    public AgentTaskService(AgentTaskMapper tasks, List<AgentResultConsumer> consumers, List<AgentTaskObserver> observers, ProjectAccess access,UserModelSettings models,
            @Value("${devproof.lease-seconds:60}") int leaseSeconds) {
        if (leaseSeconds < 15 || leaseSeconds > 300) throw new IllegalArgumentException("Invalid lease duration");
        this.tasks=tasks; this.consumers=consumers; this.observers=observers; this.access=access; this.models=models; this.leaseSeconds=leaseSeconds;
    }
    @Transactional
    public Map<String,Object> claim(String workerId, String executor, List<String> kinds) {
        if (kinds.isEmpty() || !Set.of("PLAN_DRAFT", "PLAN_REFINE", "DELIVERY_VERIFY", "DELIVERY_CLAIM_PROPOSE", "EVIDENCE_QUESTION").containsAll(kinds)) throw invalid();
        for(Map<String,Object> expired:tasks.expireExhausted())notifyStatus(expired,"FAILED","MAX_ATTEMPTS_EXCEEDED");
        Map<String,Object> task = tasks.claim(executor, String.join(",", kinds));
        if (task == null) return null;
        UUID id=(UUID)task.get("id"), attemptId=UUID.randomUUID();
        if (task.get("current_attempt_id") != null) tasks.expire((UUID)task.get("current_attempt_id"));
        if (tasks.currentAuthorization((UUID)task.get("project_id"), (UUID)task.get("created_by")) != 1) {
            tasks.fail(id, "FAILED", "AUTH_REVOKED", 0); tasks.planningStatus((UUID)task.get("planning_run_id"),"FAILED"); notifyStatus(task,"FAILED","AUTH_REVOKED"); return null;
        }
        long fence=((Number)task.get("fencing_token")).longValue()+1;
        tasks.begin(id,attemptId,workerId,fence,leaseSeconds); tasks.claimed(id,attemptId,fence);
        tasks.planningStatus((UUID)task.get("planning_run_id"),"RUNNING");
        notifyStatus(tasks.lock(id),"RUNNING",null);
        Map<String,Object> response=new LinkedHashMap<>(Json.object((String)task.get("payload_json")));
        response.putAll(Map.of("contractVersion","agent-task-v1","taskId",id,"attemptId",attemptId,"workerId",workerId,
                "fencingToken",fence,"taskKind",task.get("task_kind"),"projectId",task.get("project_id")));
        response.put("leaseExpiresAt", ((Timestamp)tasks.attempt(attemptId).get("lease_expires_at")).toInstant().toString());
        response.put("leaseDurationSeconds",leaseSeconds);
        return response;
    }
    public void version(String version) { if (!"agent-task-v1".equals(version)) throw invalid(); }
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String,Object> modelCredential(Context context) {
        Map<String,Object> task=current(tasks.lock(context.taskId()),context,true);
        Map<String,Object> payload=Json.object((String)task.get("payload_json"));
        Map<String,Object> manifest=(Map<String,Object>)payload.get("agentManifest");
        return models.runtimeCredential((UUID)task.get("created_by"),(String)manifest.get("modelConfigRef"),(Map<String,Object>)manifest.get("modelConfiguration"));
    }
    @Transactional
    public Map<String,Object> heartbeat(Context context) {
        Map<String,Object> task=tasks.lock(context.taskId());
        if (task != null && task.get("cancel_requested_at") != null) {
            current(task, context, false); return Map.of("cancelRequested",true);
        }
        current(task,context,true); tasks.heartbeat(context.attemptId(),leaseSeconds);
        return Map.of("cancelRequested",false,"leaseDurationSeconds",leaseSeconds,"leaseExpiresAt",((Timestamp)tasks.attempt(context.attemptId()).get("lease_expires_at")).toInstant().toString());
    }
    @Transactional
    public Map<String,Object> result(Context context, String snapshotJson, String schema, String hash, String candidateJson, List<UUID> evidence) {
        Map<String,Object> task=tasks.lock(context.taskId());
        if (task != null && "SUCCEEDED".equals(task.get("status"))) {
            current(task, context, false);
            if (!hash.equals(task.get("accepted_hash"))) throw new ApiProblem(409,"RESULT_CONFLICT","该执行尝试已接受其他结果");
            return Map.of("accepted",true,"resultHash",hash);
        }
        current(task,context,true);
        Map<String,Object> payload=Json.object((String)task.get("payload_json"));
        if (!Json.object(snapshotJson).equals(payload.get("inputSnapshotRef"))) throw new ApiProblem(409,"INPUT_STALE","冻结输入引用不一致");
        if (!hash.equals(Json.hash(candidateJson))) throw new ApiProblem(422,"RESULT_HASH_INVALID","结果摘要不一致");
        List<?> allowed=(List<?>)payload.get("allowedEvidenceIds");
        if (!evidence.stream().allMatch(id -> allowed.contains(id.toString()))) throw new ApiProblem(422,"CITATION_INVALID","结果引用超出授权范围");
        AgentResultConsumer consumer=consumers.stream().filter(item -> item.supports((String)task.get("task_kind"))).findFirst()
                .orElseThrow(() -> new ApiProblem(503,"TASK_HANDLER_NOT_ENABLED","该任务的正式结果处理器尚未启用"));
        if (!consumer.schemaVersion().equals(schema)) throw new ApiProblem(422,"RESULT_SCHEMA_INVALID","结果协议版本不一致");
        consumer.accept(task,Json.object(candidateJson),evidence);
        tasks.complete(context.taskId(),hash,candidateJson); tasks.attemptStatus(context.attemptId(),"SUCCEEDED");
        return Map.of("accepted",true,"resultHash",hash);
    }
    @Transactional
    public void failure(Context context, String code, String reason) {
        Map<String,Object> task=tasks.lock(context.taskId()); current(task,context,true);
        boolean retry="FAILED".equals(reason) && RETRYABLE.contains(code) && ((Number)task.get("attempt_no")).intValue()<((Number)task.get("max_attempts")).intValue();
        String status="CANCELLED".equals(reason)?"CANCELLED":retry?"QUEUED":"FAILED";
        tasks.fail(context.taskId(),status,code,Math.min(300,30*((Number)task.get("attempt_no")).intValue()));
        tasks.planningStatus((UUID)task.get("planning_run_id"),status);
        tasks.attemptStatus(context.attemptId(),status.equals("QUEUED")?"FAILED":status);
        notifyStatus(task,status,code);
    }
    @Transactional
    public void event(Context context, long sequence, String json) {
        if (sequence < 1) throw invalid();
        Map<String,Object> task=current(tasks.lock(context.taskId()),context,true);
        int inserted=tasks.event(context.taskId(),context.attemptId(),sequence,json);
        if (inserted==0 && !json.equals(tasks.eventBody(context.taskId(),context.attemptId(),sequence)))
            throw new ApiProblem(409,"EVENT_CONFLICT","相同事件序号对应不同内容");
        if(inserted==1)for(AgentTaskObserver observer:observers)if(observer.supports((String)task.get("task_kind")))observer.event(task,Json.object(json));
    }
    public Map<String,Object> current(Map<String,Object> task, Context context, boolean live) {
        if (task==null) throw new ApiProblem(404,"RESOURCE_NOT_FOUND","执行任务不存在");
        Map<String,Object> attempt=tasks.attempt(context.attemptId());
        if (!context.attemptId().equals(task.get("current_attempt_id")) || ((Number)task.get("fencing_token")).longValue()!=context.fencingToken()
                || attempt==null || !context.workerId().equals(attempt.get("worker_id"))) throw new ApiProblem(409,"ATTEMPT_STALE","执行尝试已被替换");
        if (live && (!"RUNNING".equals(task.get("status")) || task.get("cancel_requested_at")!=null || !((Timestamp)attempt.get("lease_expires_at")).after(tasks.now())))
            throw new ApiProblem(409,"LEASE_EXPIRED","租约已过期或任务已停止");
        if (live && tasks.currentAuthorization((UUID)task.get("project_id"),(UUID)task.get("created_by"))!=1)
            throw new ApiProblem(403,"AUTH_REVOKED","任务发起者授权已失效");
        return task;
    }
    @Transactional
    public Map<String,Object> toolPayload(Context context) {
        Map<String,Object> task=current(tasks.lock(context.taskId()),context,true);
        Map<String,Object> payload=Json.object((String)task.get("payload_json"));
        payload.put("projectId",task.get("project_id").toString());
        payload.put("actorId",task.get("created_by").toString());
        payload.put("taskId",context.taskId().toString()); payload.put("attemptId",context.attemptId().toString());
        payload.put("fencingToken",context.fencingToken()); payload.put("workerId",context.workerId()); return payload;
    }
    public Map<String,Object> get(UUID taskId, UUID actorId) {
        Map<String,Object> task=tasks.get(taskId);
        if (task==null) throw new ApiProblem(404,"RESOURCE_NOT_FOUND","执行任务不存在");
        String role=access.role((UUID)task.get("project_id"),actorId);
        if("EVIDENCE_QUESTION".equals(task.get("task_kind")) && !actorId.equals(task.get("created_by")) && !"ADMIN".equals(role))throw new ApiProblem(403,"AUTH_FORBIDDEN","问答任务只向发起者及项目管理员开放");
        return task;
    }
    public List<Object> events(UUID taskId, UUID actorId, long after) {
        Map<String,Object> task=get(taskId,actorId);
        if (task.get("current_attempt_id")==null) return List.of();
        return tasks.events(taskId,(UUID)task.get("current_attempt_id"),after).stream().map(Json::read).toList();
    }
    @Transactional
    public void cancel(UUID taskId, UUID actorId) {
        Map<String,Object> task=tasks.lock(taskId);
        if (task==null) throw new ApiProblem(404,"RESOURCE_NOT_FOUND","执行任务不存在");
        if("EVIDENCE_QUESTION".equals(task.get("task_kind")))access.require((UUID)task.get("project_id"),actorId);
        else access.require((UUID)task.get("project_id"),actorId,"ADMIN","SUBMITTER");
        if (!"DELIVERY_VERIFY".equals(task.get("task_kind")) && !actorId.equals(task.get("created_by"))) access.require((UUID)task.get("project_id"),actorId,"ADMIN");
        if (!Set.of("QUEUED","RUNNING").contains(task.get("status"))) throw new ApiProblem(409,"STATE_CONFLICT","终态任务不能取消");
        tasks.cancel(taskId);
        tasks.planningStatus((UUID)task.get("planning_run_id"),"CANCELLED");
        if (task.get("current_attempt_id")!=null) tasks.attemptStatus((UUID)task.get("current_attempt_id"),"CANCELLED");
        notifyStatus(task,"CANCELLED","RUN_CANCELLED");
    }
    private void notifyStatus(Map<String,Object> task,String status,String code) {
        for(AgentTaskObserver observer:observers)if(observer.supports((String)task.get("task_kind")))observer.status(task,status,code);
    }
    public record Context(UUID taskId, UUID attemptId, long fencingToken, String workerId) {}
    private ApiProblem invalid() { return new ApiProblem(422,"CONTRACT_INVALID","任务协议参数无效"); }
}
