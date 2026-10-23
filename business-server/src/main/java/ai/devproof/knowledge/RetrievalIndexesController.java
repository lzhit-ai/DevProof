package ai.devproof.knowledge;

import ai.devproof.infrastructure.CommandStore;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}/retrieval-indexes")
public class RetrievalIndexesController {
    private final IndexBuildStore store;
    private final ComputeClient compute;
    public RetrievalIndexesController(IndexBuildStore store,ComputeClient compute) { this.store=store; this.compute=compute; }
    @GetMapping public List<Map<String,Object>> list(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return store.list(project,actor); }
    @GetMapping("/rebuild-runs") public List<Map<String,Object>> runs(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return store.runs(project,actor); }
    @PostMapping("/rebuild") public ResponseEntity<?> rebuild(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,
        @RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        var command=CommandStore.context(request,key,raw); var replay=store.preflight(project,actor,command);
        if(replay!=null)return ResponseEntity.status(replay.status()).body(replay.body());
        var result=store.enqueue(project,actor,command,compute.configuration()); return ResponseEntity.status(result.status()).body(result.body());
    }
}
