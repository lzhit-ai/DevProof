package ai.devproof.securitybaseline;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}/peripheral-profile-runs")
public class PeripheralController {
    private final PeripheralRuns runs;
    public PeripheralController(PeripheralRuns runs) { this.runs=runs; }
    @PostMapping public ResponseEntity<?> create(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) { var result=runs.create(project,actor,ApiInput.object(raw),CommandStore.context(request,key,raw));return ResponseEntity.status(result.status()).body(result.body()); }
    @GetMapping public List<Map<String,Object>> list(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestParam(value="assessment_profile",required=false) String profile) { return runs.list(project,actor,profile); }
}
