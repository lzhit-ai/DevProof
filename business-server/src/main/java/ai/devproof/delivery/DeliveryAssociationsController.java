package ai.devproof.delivery;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{project}/delivery-items/{item}")
public class DeliveryAssociationsController {
    private final DeliveryAssociations associations;
    public DeliveryAssociationsController(DeliveryAssociations associations) { this.associations=associations; }
    @GetMapping("/change-links") public List<Map<String,Object>> links(@PathVariable UUID project,@PathVariable UUID item,@RequestAttribute("actorId") UUID actor) { return associations.links(project,item,actor); }
    @GetMapping("/agent-change-candidate-targets") public List<Map<String,Object>> targets(@PathVariable UUID project,@PathVariable UUID item,@RequestAttribute("actorId") UUID actor) { return associations.targets(project,item,actor); }
    @PostMapping("/change-links") public ResponseEntity<?> confirm(@PathVariable UUID project,@PathVariable UUID item,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); UUID pr=ApiInput.optionalUuid(body,"pull_request_resource_id"),git=ApiInput.optionalUuid(body,"git_snapshot_id");
        if((pr==null)==(git==null))throw ApiInput.invalid();
        String reason=body.containsKey("reason")?ApiInput.text(body,"reason",0,4000):"";
        return response(associations.confirm(project,item,actor,CommandStore.context(request,key,raw),new DeliveryAssociations.Selection(pr!=null?"PULL_REQUEST":"GIT_SNAPSHOT",pr!=null?pr:git),reason));
    }
    @PostMapping("/agent-change-candidates") public ResponseEntity<?> propose(@PathVariable UUID project,@PathVariable UUID item,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw);
        if(!(body.get("targets") instanceof List<?> targets) || targets.isEmpty() || targets.size()>20)throw ApiInput.invalid();
        List<DeliveryAssociations.Selection> selections=new ArrayList<>(); Set<DeliveryAssociations.Selection> unique=new HashSet<>();
        for(Object value:targets) {
            if(!(value instanceof Map<?,?> target) || !(target.get("target_kind") instanceof String kind) || !Set.of("PULL_REQUEST","GIT_SNAPSHOT").contains(kind))throw ApiInput.invalid();
            var selection=new DeliveryAssociations.Selection(kind,ApiInput.uuid(target.get("target_id"))); if(!unique.add(selection))throw ApiInput.invalid(); selections.add(selection);
        }
        return response(associations.propose(project,item,actor,CommandStore.context(request,key,raw),List.copyOf(selections)));
    }
    @PostMapping("/discover-platform-links") public ResponseEntity<?> discover(@PathVariable UUID project,@PathVariable UUID item,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(associations.discover(project,item,actor,CommandStore.context(request,key,raw)));
    }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
