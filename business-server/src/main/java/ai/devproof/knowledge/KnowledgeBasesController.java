package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class KnowledgeBasesController {
    private final KnowledgeBases bases;
    public KnowledgeBasesController(KnowledgeBases bases) { this.bases=bases; }
    @GetMapping("/api/v1/knowledge-bases") public List<Map<String,Object>> all(@RequestAttribute("actorId") UUID actor) { return bases.all(actor); }
    @GetMapping("/api/v1/projects/{project}/knowledge-bases") public List<Map<String,Object>> list(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return bases.list(project,actor); }
    @PostMapping("/api/v1/projects/{project}/knowledge-bases") public ResponseEntity<?> create(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var result=bases.create(project,actor,CommandStore.context(request,key,raw),ApiInput.text(ApiInput.object(raw),"name",1,255));
        return ResponseEntity.status(result.status()).body(result.body());
    }
    @PostMapping("/api/v1/projects/{project}/knowledge-bases/mount") public ResponseEntity<?> mount(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var result=bases.mount(project,ApiInput.uuid(ApiInput.object(raw).get("knowledge_base_id")),actor,CommandStore.context(request,key,raw));
        return ResponseEntity.status(result.status()).body(result.body());
    }
    @DeleteMapping("/api/v1/projects/{project}/knowledge-bases/{base}") public ResponseEntity<Void> unmount(@PathVariable UUID project,@PathVariable UUID base,@RequestAttribute("actorId") UUID actor,HttpServletRequest request) {
        bases.unmount(project,base,actor,CommandStore.context(request,null,null).correlationId()); return ResponseEntity.noContent().build();
    }
}
