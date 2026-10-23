package ai.devproof.knowledge;

import ai.devproof.agentjob.WorkerAuth;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

/** Internal execution diagnostics; source availability does not determine report/API readiness. */
@RestController
public class ComputeStatusController {
    private final ComputeClient client;
    private final WorkerAuth workers;
    public ComputeStatusController(ComputeClient client,WorkerAuth workers) { this.client=client; this.workers=workers; }
    @GetMapping("/internal/v1/compute/status")
    public Map<String,Object> status(@RequestHeader(value="Authorization",required=false) String authorization,
                                    @RequestHeader("X-Worker-Id") String worker) {
        workers.require(authorization,worker); var configuration=client.configuration();
        return Map.of("status","AVAILABLE","configurationHash",configuration.hash(),
            "embeddingCredentialConfigured",configuration.embeddingConfigured(),"mineruCredentialConfigured",configuration.mineruConfigured());
    }
}
