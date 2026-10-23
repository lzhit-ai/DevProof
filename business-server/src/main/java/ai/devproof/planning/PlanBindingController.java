package ai.devproof.planning;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{projectId}")
public class PlanBindingController {
    private final PlanBindingService bindings;
    public PlanBindingController(PlanBindingService bindings) { this.bindings=bindings; }
    public record Mapping(@NotBlank @Size(max=100) String issueKey,@NotBlank @Size(max=100) String acceptanceKey,@NotNull UUID claimId) {}
    public record Selection(@NotNull UUID planVersionId,@NotBlank String planContentHash,UUID expectedSelectionId,@NotEmpty @Size(max=12) List<@Valid Mapping> mappings) {}
    public record Clear(UUID expectedSelectionId) {}
    @GetMapping("/plan-options")
    public List<Map<String,Object>> options(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId) {
        return bindings.options(projectId,actorId);
    }
    @GetMapping("/plans/{planId}")
    public Map<String,Object> plan(@PathVariable UUID projectId,@PathVariable UUID planId,@RequestAttribute("actorId") UUID actorId) {
        return bindings.plan(projectId,planId,actorId);
    }
    @GetMapping("/cycles/{cycleId}/plan-selection")
    public Map<String,Object> current(@PathVariable UUID projectId,@PathVariable UUID cycleId,@RequestAttribute("actorId") UUID actorId) {
        return bindings.get(projectId,cycleId,actorId);
    }
    @PostMapping("/cycles/{cycleId}/plan-selection")
    public Map<String,Object> select(@PathVariable UUID projectId,@PathVariable UUID cycleId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody Selection input) {
        return bindings.bind(projectId,cycleId,actorId,input.planVersionId(),input.planContentHash(),input.expectedSelectionId(),input.mappings().stream()
            .map(item->new PlanBindingService.Binding(item.issueKey(),item.acceptanceKey(),item.claimId())).toList());
    }
    @DeleteMapping("/cycles/{cycleId}/plan-selection")
    public Map<String,Object> clear(@PathVariable UUID projectId,@PathVariable UUID cycleId,@RequestAttribute("actorId") UUID actorId,@RequestBody Clear input) {
        return bindings.clear(projectId,cycleId,actorId,input.expectedSelectionId());
    }
    @GetMapping("/cycles/{cycleId}/plan-trace")
    public Map<String,Object> trace(@PathVariable UUID projectId,@PathVariable UUID cycleId,@RequestAttribute("actorId") UUID actorId) {
        return bindings.trace(projectId,cycleId,actorId);
    }
}
