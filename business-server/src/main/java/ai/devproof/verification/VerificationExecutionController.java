package ai.devproof.verification;

import ai.devproof.infrastructure.CommandStore;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class VerificationExecutionController {
    private final VerificationExecution execution;
    public VerificationExecutionController(VerificationExecution execution) { this.execution=execution; }
    @PostMapping("/api/v1/input-snapshots/{snapshot}/analysis-runs")
    public ResponseEntity<?> start(@PathVariable UUID snapshot,@RequestAttribute("actorId") UUID actor,
            @RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        CommandStore.Result result=execution.start(snapshot,actor,CommandStore.context(request,key,raw));
        return ResponseEntity.status(result.status()).body(result.body());
    }
    @PostMapping("/api/v1/analysis-runs/{run}/cancel")
    public Map<String,Object> cancel(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor) { return execution.cancel(run,actor); }
}
