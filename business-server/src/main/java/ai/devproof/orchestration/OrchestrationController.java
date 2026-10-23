package ai.devproof.orchestration;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class OrchestrationController {
    private final OrchestrationManagement commands;
    private final OrchestrationQueries queries;
    public OrchestrationController(OrchestrationManagement commands,OrchestrationQueries queries) { this.commands=commands; this.queries=queries; }
    @GetMapping("/api/v1/projects/{project}/agent-orchestration") public Map<String,Object> list(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return queries.list(project,actor); }
    @GetMapping("/api/v1/projects/{project}/agent-orchestration/task-bindings") public List<Map<String,Object>> bindings(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return queries.bindings(project,actor); }
    @GetMapping("/api/v1/projects/{project}/agent-orchestration/capabilities/{capability}/latest-version") public Map<String,Object> latest(@PathVariable UUID project,@PathVariable UUID capability,@RequestAttribute("actorId") UUID actor) { return queries.latest(project,capability,actor); }
    @PostMapping("/api/v1/projects/{project}/agent-orchestration/tools") public ResponseEntity<?> tool(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(commands.tool(project,actor,CommandStore.context(request,key,raw),ApiInput.object(raw)));
    }
    @PostMapping("/api/v1/projects/{project}/agent-orchestration/capabilities") public ResponseEntity<?> capability(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(commands.capability(project,actor,CommandStore.context(request,key,raw),ApiInput.object(raw)));
    }
    @PostMapping("/api/v1/projects/{project}/agent-orchestration/capabilities/{capability}/versions") public ResponseEntity<?> version(@PathVariable UUID project,@PathVariable UUID capability,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(commands.nextVersion(project,capability,actor,CommandStore.context(request,key,raw),ApiInput.object(raw)));
    }
    @PostMapping("/api/v1/projects/{project}/agent-orchestration/capabilities/{capability}/deactivate") public ResponseEntity<?> deactivate(@PathVariable UUID project,@PathVariable UUID capability,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(commands.deactivate(project,capability,actor,CommandStore.context(request,key,raw)));
    }
    @PostMapping("/api/v1/projects/{project}/agent-orchestration/templates") public ResponseEntity<?> template(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(commands.template(project,actor,CommandStore.context(request,key,raw),ApiInput.object(raw)));
    }
    @PutMapping("/api/v1/verification-tasks/{task}/agent-orchestration") public ResponseEntity<?> bind(@PathVariable UUID task,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(commands.bind(task,ApiInput.uuid(ApiInput.object(raw).get("template_id")),actor,CommandStore.context(request,key,raw)));
    }
    @GetMapping("/api/v1/analysis-runs/{run}/orchestration") public Map<String,Object> run(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor) { return queries.run(run,actor); }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
