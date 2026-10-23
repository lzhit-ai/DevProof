package ai.devproof.task;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}/verification-tasks")
public class TasksController {
    private final TaskManagement tasks;
    public TasksController(TaskManagement tasks) { this.tasks=tasks; }
    @GetMapping public List<Map<String,Object>> list(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return tasks.list(project,actor); }
    @PostMapping public ResponseEntity<?> create(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        Map<String,Object> input=ApiInput.object(raw);
        return response(tasks.create(project,actor,CommandStore.context(request,key,raw),ApiInput.text(input,"title",1,300),ApiInput.text(input,"requirement_key",1,100),ApiInput.uuid(input.get("delivery_item_id")),ApiInput.optionalUuid(input,"orchestration_template_id")));
    }
    @PostMapping("/{task}/cycles") public ResponseEntity<?> cycle(@PathVariable UUID project,@PathVariable UUID task,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(tasks.nextCycle(project,task,actor,CommandStore.context(request,key,raw)));
    }
    @PutMapping("/{task}/delivery-item") public ResponseEntity<?> delivery(@PathVariable UUID project,@PathVariable UUID task,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(tasks.bindDelivery(project,task,actor,CommandStore.context(request,key,raw),ApiInput.uuid(ApiInput.object(raw).get("delivery_item_id"))));
    }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
