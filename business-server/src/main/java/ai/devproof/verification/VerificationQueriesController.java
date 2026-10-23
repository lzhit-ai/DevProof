package ai.devproof.verification;

import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class VerificationQueriesController {
    private final VerificationQueries queries;
    public VerificationQueriesController(VerificationQueries queries) { this.queries=queries; }
    @GetMapping("/api/v1/analysis-runs/{run}") public Map<String,Object> run(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor) { return queries.run(run,actor); }
    @GetMapping("/api/v1/verification-tasks/{task}/latest-analysis-run") public Map<String,Object> latest(@PathVariable UUID task,@RequestAttribute("actorId") UUID actor) { return queries.latest(task,actor); }
    @GetMapping("/api/v1/analysis-runs/{run}/events") public Map<String,Object> events(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor,@RequestParam(required=false) UUID before,@RequestParam(defaultValue="200") int limit) { return queries.events(run,actor,before,limit); }
    @GetMapping("/api/v1/analysis-runs/{run}/results") public List<Map<String,Object>> results(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor) { return queries.results(run,actor); }
    @GetMapping("/api/v1/analysis-runs/{run}/code-review") public Map<String,Object> codeReview(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor) { return queries.codeReview(run,actor); }
}
