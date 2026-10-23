package ai.devproof.planning;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{projectId}")
public class RepositorySnapshotController {
    private final RepositorySnapshotService snapshots;
    public RepositorySnapshotController(RepositorySnapshotService snapshots) { this.snapshots=snapshots; }
    public record Capture(@NotNull UUID repositoryId, @NotBlank @Size(max=255) String ref) {}
    @GetMapping("/planning-repositories")
    public List<Map<String,Object>> repositories(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId) { return snapshots.repositories(projectId,actorId); }
    @GetMapping("/repository-snapshots")
    public List<Map<String,Object>> list(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId) { return snapshots.list(projectId,actorId); }
    @PostMapping("/repository-snapshots")
    public Map<String,Object> capture(@PathVariable UUID projectId,@RequestAttribute("actorId") UUID actorId,@Valid @RequestBody Capture input) {
        return snapshots.capture(projectId,input.repositoryId(),input.ref(),actorId);
    }
}
