package ai.devproof.delivery;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}/verification-tasks/{task}/delivery-claims")
public class DeliveryClaimsController {
    private final DeliveryClaims claims;
    public DeliveryClaimsController(DeliveryClaims claims) { this.claims=claims; }
    @GetMapping public List<Map<String,Object>> list(@PathVariable UUID project,@PathVariable UUID task,@RequestAttribute("actorId") UUID actor) { return claims.list(project,task,actor); }
    @GetMapping("/proposal-runs") public List<Map<String,Object>> runs(@PathVariable UUID project,@PathVariable UUID task,@RequestAttribute("actorId") UUID actor) { return claims.runs(project,task,actor); }
    @PostMapping("/propose") public ResponseEntity<?> propose(@PathVariable UUID project,@PathVariable UUID task,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); var sources=ApiInput.uuids(body,"source_revision_ids",20);
        if(new HashSet<>(sources).size()!=sources.size())throw ApiInput.invalid();
        var result=claims.propose(project,task,actor,CommandStore.context(request,key,raw),sources); return ResponseEntity.status(result.status()).body(result.body());
    }
    @PutMapping public ResponseEntity<?> confirm(@PathVariable UUID project,@PathVariable UUID task,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw);
        if(!(body.get("claims") instanceof List<?> values) || values.isEmpty() || values.size()>12)throw ApiInput.invalid();
        List<DeliveryClaims.Confirmation> selections=new ArrayList<>();
        for(Object value:values) {
            if(!(value instanceof Map<?,?> map))throw ApiInput.invalid();
            @SuppressWarnings("unchecked") var claim=(Map<String,Object>)map;
            selections.add(new DeliveryClaims.Confirmation(ApiInput.optionalUuid(claim,"id"),ApiInput.text(claim,"text",3,6000)));
        }
        var result=claims.confirm(project,task,actor,CommandStore.context(request,key,raw),List.copyOf(selections)); return ResponseEntity.status(result.status()).body(result.body().get("claims"));
    }
}
