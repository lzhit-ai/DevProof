package ai.devproof.status;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}")
public class ProjectStatusController {
    private final ProjectStatus status;
    public ProjectStatusController(ProjectStatus status) { this.status=status; }
    @PostMapping("/health-snapshots") public ResponseEntity<?> create(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw);return response(status.createHealth(project,actor,ApiInput.optionalText(body,"milestone_key",160),CommandStore.context(request,key,raw)));
    }
    @GetMapping("/health-snapshots") public List<Map<String,Object>> snapshots(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return status.healthList(project,actor); }
    @GetMapping("/health-snapshots/{id}") public Map<String,Object> snapshot(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) { return status.health(project,id,actor); }
    @PostMapping("/project-summary-drafts") public ResponseEntity<?> createDraft(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw);return response(status.createDraft(project,actor,ApiInput.uuid(body.get("health_snapshot_id")),ApiInput.text(body,"period_type",1,24),ApiInput.optionalText(body,"title",300),CommandStore.context(request,key,raw)));
    }
    @GetMapping("/project-summary-drafts") public List<Map<String,Object>> drafts(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return status.drafts(project,actor); }
    @PostMapping("/project-summary-drafts/{id}/publish") public ResponseEntity<?> publish(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        if(raw!=null && raw.length>0 && !ApiInput.object(raw).isEmpty())throw ApiInput.invalid();return response(status.publish(project,id,actor,CommandStore.context(request,key,raw)));
    }
    @GetMapping("/project-summary-records") public List<Map<String,Object>> records(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return status.records(project,actor); }
    private static ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
