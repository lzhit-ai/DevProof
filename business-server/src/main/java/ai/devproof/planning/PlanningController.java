package ai.devproof.planning;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{projectId}")
public class PlanningController {
    private final PlanningService planning;
    public PlanningController(PlanningService planning) { this.planning=planning; }
    public record IdeaInput(@NotBlank @Size(max=300) String title,@NotBlank @Size(max=40000) String content) {}
    public record IdeaRevision(@Min(1) int expectedVersion,@NotBlank @Size(max=300) String title,@NotBlank @Size(max=40000) String content) {}
    public record Start(@NotNull UUID repositorySnapshotId,@Min(1) int expectedIdeaVersion) {}
    public record Answer(@NotNull UUID questionId,@NotBlank @Size(max=12000) String answer) {}
    public record Answers(@NotEmpty @Size(max=30) List<@Valid Answer> answers) {}
    public record Edit(@Min(1) int expectedVersion,@NotNull Map<String,Object> body) {}
    public record Confirm(@Min(1) int expectedVersion,@NotBlank String contentHash) {}
    @GetMapping("/planning-permissions")
    public Map<String,Object> permissions(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId) { return planning.permissions(projectId,actorId); }
    @GetMapping("/ideas")
    public List<Map<String,Object>> list(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId) { return planning.list(projectId,actorId); }
    @PostMapping("/ideas")
    public Map<String,Object> create(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody IdeaInput input) {
        return planning.create(projectId,actorId,input.title(),input.content());
    }
    @GetMapping("/ideas/{ideaId}")
    public Map<String,Object> detail(@PathVariable UUID projectId,@PathVariable UUID ideaId,@RequestAttribute("actorId") UUID actorId) {
        return planning.detail(projectId,ideaId,actorId);
    }
    @PutMapping("/ideas/{ideaId}")
    public Map<String,Object> revise(@PathVariable UUID projectId,@PathVariable UUID ideaId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody IdeaRevision input) {
        return planning.revise(projectId,ideaId,actorId,input.expectedVersion(),input.title(),input.content());
    }
    @PostMapping("/ideas/{ideaId}/planning-runs")
    public Map<String,Object> start(@PathVariable UUID projectId,@PathVariable UUID ideaId,@RequestAttribute("actorId") UUID actorId,
            @RequestHeader("Idempotency-Key") String key,@Valid @RequestBody Start input) {
        return planning.start(projectId,ideaId,actorId,input.repositorySnapshotId(),input.expectedIdeaVersion(),key);
    }
    @PostMapping("/ideas/{ideaId}/answers")
    public Map<String,Object> answers(@PathVariable UUID projectId,@PathVariable UUID ideaId,@RequestAttribute("actorId") UUID actorId,
            @RequestHeader("Idempotency-Key") String key,@Valid @RequestBody Answers input) {
        return planning.answers(projectId,ideaId,actorId,input.answers().stream().map(answer->new PlanningService.Answer(answer.questionId(),answer.answer())).toList(),key);
    }
    @PutMapping("/plans/{planId}")
    public Map<String,Object> edit(@PathVariable UUID projectId,@PathVariable UUID planId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody Edit input) {
        return planning.edit(projectId,planId,actorId,input.expectedVersion(),input.body());
    }
    @PostMapping("/plans/{planId}/revisions")
    public Map<String,Object> version(@PathVariable UUID projectId,@PathVariable UUID planId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody Edit input) {
        return planning.newVersion(projectId,planId,actorId,input.expectedVersion(),input.body());
    }
    @PostMapping("/plans/{planId}/confirm")
    public Map<String,Object> confirm(@PathVariable UUID projectId,@PathVariable UUID planId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody Confirm input) {
        return planning.confirm(projectId,planId,actorId,input.expectedVersion(),input.contentHash());
    }
    @GetMapping("/ideas/{ideaId}/plan-diff")
    public Map<String,Object> diff(@PathVariable UUID projectId,@PathVariable UUID ideaId,@RequestAttribute("actorId") UUID actorId,
            @RequestParam UUID from,@RequestParam UUID to) { return planning.diff(projectId,ideaId,actorId,from,to); }
}
