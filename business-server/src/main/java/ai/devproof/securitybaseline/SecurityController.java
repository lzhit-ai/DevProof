package ai.devproof.securitybaseline;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}")
public class SecurityController {
    private final SecurityBaselines security;
    public SecurityController(SecurityBaselines security) { this.security=security; }
    @PostMapping("/security-scan-artifacts") public ResponseEntity<?> create(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) { return response(security.importScan(project,actor,ApiInput.object(raw),CommandStore.context(request,key,raw))); }
    @GetMapping("/security-scan-artifacts") public List<Map<String,Object>> scans(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return security.scans(project,actor); }
    @GetMapping("/security-scan-artifacts/{id}/findings") public List<Map<String,Object>> findings(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) { return security.findings(project,id,actor); }
    @GetMapping("/security-scan-artifacts/{id}/explanation") public Map<String,Object> explain(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) { return security.explain(project,id,actor); }
    @GetMapping("/quality-trend") public Map<String,Object> trend(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return security.trend(project,actor); }
    @PutMapping("/security-findings/{id}/status") public ResponseEntity<?> status(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw);return response(security.status(project,id,actor,ApiInput.text(body,"finding_status",1,32),ApiInput.text(body,"reason",1,4000),CommandStore.context(request,key,raw)));
    }
    @PostMapping("/security-baselines") public ResponseEntity<?> baseline(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw);return response(security.createBaseline(project,actor,ApiInput.uuid(body.get("repository_id")),SecurityBaselines.sha(body),ApiInput.uuids(body,"scan_artifact_ids",100),CommandStore.context(request,key,raw)));
    }
    @GetMapping("/security-baselines") public List<Map<String,Object>> baselines(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return security.baselines(project,actor); }
    @PostMapping("/security-baselines/{id}/confirm") public ResponseEntity<?> confirm(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) { var body=ApiInput.object(raw);return response(security.confirm(project,id,actor,ApiInput.text(body,"reason",1,4000),CommandStore.context(request,key,raw))); }
    @GetMapping("/security-baseline-records") public List<Map<String,Object>> records(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return security.records(project,actor); }
    private static ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
