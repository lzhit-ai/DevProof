package ai.devproof.infrastructure;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties("devproof")
public record DevProofProperties(
        @Size(min = 32) String jwtSecret,
        @Min(300) long tokenTtlSeconds,
        @Min(1) long reportCacheTtlSeconds,
        @Min(1024) long reportCacheMaxBytes,
        String corsOrigins,
        String workerToken) {}
