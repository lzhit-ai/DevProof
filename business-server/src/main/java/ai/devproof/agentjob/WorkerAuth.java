package ai.devproof.agentjob;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.DevProofProperties;
import ai.devproof.infrastructure.Json;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class WorkerAuth {
    private final Map<String, Object> credentials;
    public WorkerAuth(DevProofProperties config) {
        credentials = config.workerToken() == null || config.workerToken().isBlank() ? Map.of() : Json.object(config.workerToken());
        for (Object token : credentials.values()) {
            if (!(token instanceof String value) || value.length() < 32) throw new IllegalArgumentException("Worker credentials must contain at least 32 characters");
        }
    }
    public void require(String authorization, String workerId) {
        if (credentials.isEmpty()) throw new ApiProblem(503, "WORKER_AUTH_NOT_CONFIGURED", "尚未配置 Worker 身份凭据");
        Object expected = credentials.get(workerId);
        String supplied = authorization != null && authorization.startsWith("Bearer ") ? authorization.substring(7) : "";
        if (!(expected instanceof String token) || !MessageDigest.isEqual(token.getBytes(StandardCharsets.UTF_8), supplied.getBytes(StandardCharsets.UTF_8)))
            throw new ApiProblem(401, "WORKER_AUTH_INVALID", "Worker 身份校验失败");
    }
}
