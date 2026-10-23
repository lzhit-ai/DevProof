package ai.devproof.source;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}")
public class GitHubSourcesController {
    private final GitHubSources sources;
    public GitHubSourcesController(GitHubSources sources) { this.sources=sources; }
    @GetMapping("/external-connections") public List<Map<String,Object>> connections(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return sources.connections(project,actor); }
    @PostMapping("/external-connections") public ResponseEntity<?> create(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        Map<String,Object> body=ApiInput.object(raw); String provider=body.containsKey("provider")?ApiInput.text(body,"provider",1,32):"GITHUB";
        return response(sources.create(project,actor,CommandStore.context(request,key,raw),provider,ApiInput.text(body,"name",1,160),ApiInput.text(body,"repository_slug",3,255),ApiInput.optionalText(body,"secret_ref",160)));
    }
    @PostMapping("/external-connections/{connection}/sync") public ResponseEntity<?> sync(@PathVariable UUID project,@PathVariable UUID connection,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(sources.queue(project,connection,actor,CommandStore.context(request,key,raw)));
    }
    @GetMapping("/source-sync-runs") public List<Map<String,Object>> runs(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return sources.runs(project,actor); }
    @GetMapping("/delivery-items") public List<Map<String,Object>> deliveries(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return sources.deliveries(project,actor); }
    @GetMapping("/delivery-items/{delivery}/source-links") public List<Map<String,Object>> links(@PathVariable UUID project,@PathVariable UUID delivery,@RequestAttribute("actorId") UUID actor) { return sources.links(project,delivery,actor); }
    @PostMapping("/delivery-items/{delivery}/source-links") public ResponseEntity<?> link(@PathVariable UUID project,@PathVariable UUID delivery,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        Map<String,Object> body=ApiInput.object(raw); return response(sources.linkDocument(project,delivery,actor,CommandStore.context(request,key,raw),ApiInput.uuid(body.get("source_revision_id")),ApiInput.text(body,"link_role",1,32)));
    }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
