package ai.devproof.agentjob;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;

@RestController
public class AgentTaskController {
    private final WorkerAuth workers;
    private final AgentTaskService service;
    private final List<AgentTaskTool> tools;
    public AgentTaskController(WorkerAuth workers, AgentTaskService service, List<AgentTaskTool> tools) {
        this.workers=workers; this.service=service; this.tools=tools;
    }
    @PostMapping("/internal/v1/agent-tasks/claim")
    public Map<String,Object> claim(@RequestHeader(value="Authorization",required=false) String authorization, @RequestBody Map<String,Object> body) {
        service.version(text(body,"contractVersion"));
        workers.require(authorization,text(body,"workerId"));
        return service.claim(text(body,"workerId"),text(body,"executorVersion"),array(body,"taskKinds").stream().map(value -> (String)value).toList());
    }
    @PostMapping("/internal/v1/agent-tasks/{taskId}/heartbeat")
    public Map<String,Object> heartbeat(@PathVariable UUID taskId, @RequestHeader(value="Authorization",required=false) String authorization, @RequestBody Map<String,Object> body) {
        return service.heartbeat(context(authorization,taskId,body));
    }
    @PostMapping("/internal/v1/agent-tasks/{taskId}/model-credential")
    public ResponseEntity<?> modelCredential(@PathVariable UUID taskId,@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> body) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.modelCredential(context(authorization,taskId,body)));
    }
    @PostMapping("/internal/v1/agent-tasks/{taskId}/result")
    public Map<String,Object> result(@PathVariable UUID taskId, @RequestHeader(value="Authorization",required=false) String authorization, @RequestBody Map<String,Object> body) {
        AgentTaskService.Context context=context(authorization,taskId,body);
        return service.result(context,Json.write(object(body,"inputSnapshotRef")),text(body,"resultSchemaVersion"),text(body,"resultHash"),
                text(body,"candidatesJson"),array(body,"evidenceRefs").stream().map(value -> uuid(value)).toList());
    }
    @PostMapping("/internal/v1/agent-tasks/{taskId}/failure")
    public Map<String,Object> failure(@PathVariable UUID taskId, @RequestHeader(value="Authorization",required=false) String authorization, @RequestBody Map<String,Object> body) {
        AgentTaskService.Context context=context(authorization,taskId,body);
        String reason=text(body,"reason");
        if (!Set.of("FAILED","CANCELLED","BUDGET_EXHAUSTED").contains(reason)) throw invalid();
        service.failure(context,text(body,"errorCode"),reason); return Map.of("accepted",true);
    }
    @PostMapping("/internal/v1/agent-tasks/{taskId}/events")
    public Map<String,Object> event(@PathVariable UUID taskId, @RequestHeader(value="Authorization",required=false) String authorization, @RequestBody Map<String,Object> body) {
        AgentTaskService.Context context=context(authorization,taskId,body);
        uuid(body.get("agentInstanceId"));
        java.time.OffsetDateTime.parse(text(body,"occurredAt"));
        service.event(context,number(body,"eventSeq"),Json.write(body)); return Map.of("accepted",true);
    }
    @PostMapping("/internal/v1/agent-tools/{toolKey}/execute")
    public Object tool(@PathVariable String toolKey, @RequestHeader(value="Authorization",required=false) String authorization, @RequestBody Map<String,Object> body) {
        AgentTaskService.Context context=context(authorization,uuid(body.get("taskId")),body);
        Map<String,Object> payload=service.toolPayload(context);
        if (!object(body,"inputSnapshotRef").equals(payload.get("inputSnapshotRef"))) throw new ApiProblem(409,"INPUT_STALE","工具输入范围不一致");
        Map<String,Object> spec=object(body,"tool");
        if (!toolKey.equals(text(spec,"key"))) throw invalid();
        Map<String,Object> manifest=object(payload,"agentManifest");
        if (!array(manifest,"tools").contains(spec)) throw new ApiProblem(403,"TOOL_FORBIDDEN","工具未授权");
        AgentTaskTool tool=tools.stream().filter(item -> item.key().equals(toolKey) && item.version().equals(spec.get("version"))).findFirst()
                .orElseThrow(() -> new ApiProblem(404,"TOOL_NOT_FOUND","注册工具不存在"));
        return tool.execute(payload,object(body,"arguments"));
    }
    @GetMapping("/api/v1/agent-tasks/{taskId}")
    public Map<String,Object> get(@PathVariable UUID taskId,@RequestAttribute("actorId") UUID actorId) { return service.get(taskId,actorId); }
    @GetMapping("/api/v1/agent-tasks/{taskId}/events")
    public List<Object> events(@PathVariable UUID taskId,@RequestAttribute("actorId") UUID actorId,@RequestParam(defaultValue="0") long after) {
        if (after<0) throw invalid(); return service.events(taskId,actorId,after);
    }
    @PostMapping("/api/v1/agent-tasks/{taskId}/cancel")
    public Map<String,Object> cancel(@PathVariable UUID taskId,@RequestAttribute("actorId") UUID actorId) { service.cancel(taskId,actorId); return Map.of("cancelled",true); }

    private AgentTaskService.Context context(String authorization, UUID taskId, Map<String,Object> body) {
        service.version(text(body,"contractVersion"));
        String worker=text(body,"workerId"); workers.require(authorization,worker);
        if (!taskId.equals(uuid(body.get("taskId")))) throw invalid();
        long fence=number(body,"fencingToken"); if (fence<1) throw invalid();
        return new AgentTaskService.Context(taskId,uuid(body.get("attemptId")),fence,worker);
    }
    static String text(Map<String,Object> body,String key) {
        if (!(body.get(key) instanceof String value) || value.isBlank()) throw invalid(); return value;
    }
    @SuppressWarnings("unchecked") static Map<String,Object> object(Map<String,Object> body,String key) {
        if (!(body.get(key) instanceof Map<?,?> value)) throw invalid(); return (Map<String,Object>)value;
    }
    static List<?> array(Map<String,Object> body,String key) { if (!(body.get(key) instanceof List<?> value)) throw invalid(); return value; }
    static UUID uuid(Object value) { try { return UUID.fromString((String)value); } catch (RuntimeException e) { throw invalid(); } }
    static long number(Map<String,Object> body,String key) { if (!(body.get(key) instanceof Number value) || value.doubleValue()!=value.longValue()) throw invalid(); return value.longValue(); }
    private static ApiProblem invalid() { return new ApiProblem(422,"CONTRACT_INVALID","任务协议参数无效"); }
}
