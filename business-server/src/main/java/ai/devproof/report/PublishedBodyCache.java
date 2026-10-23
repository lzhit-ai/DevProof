package ai.devproof.report;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.DevProofProperties;
import ai.devproof.infrastructure.Json;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PublishedBodyCache {
    private static final Logger LOG = LoggerFactory.getLogger(PublishedBodyCache.class);
    private final StringRedisTemplate redis;
    private final ReportMapper reports;
    private final DevProofProperties config;
    public PublishedBodyCache(StringRedisTemplate redis, ReportMapper reports, DevProofProperties config) {
        this.redis = redis; this.reports = reports; this.config = config;
    }

    // Caller authorizes project/record membership before even reading cache metadata.
    public Map<String, Object> read(UUID projectId, UUID reportId) {
        Map<String, Object> metadata = reports.bodyMetadata(reportId);
        if (metadata == null) return null;
        String hash = (String) metadata.get("content_hash");
        String schema = (String) metadata.get("schema_version");
        String key = "review:published-body:" + projectId + ":" + reportId + ":" + hash + ":" + schema;
        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                Map<String, Object> body = decode(cached, reportId, hash, schema);
                if (body != null) { LOG.debug("published_body_cache_hit report_id={}", reportId); return body; }
            }
        } catch (DataAccessException e) { LOG.warn("published_body_cache_read_unavailable report_id={}", reportId); }
        String stored = reports.body(reportId);
        Map<String, Object> body = stored == null ? null : decode(stored, reportId, hash, schema);
        if (body == null) throw new ApiProblem(409, "REPORT_BODY_INVALID", "已发布正文缺失或摘要校验失败");
        if (stored.getBytes(StandardCharsets.UTF_8).length <= config.reportCacheMaxBytes()) {
            try { redis.opsForValue().set(key, stored, Duration.ofSeconds(config.reportCacheTtlSeconds())); }
            catch (DataAccessException e) { LOG.warn("published_body_cache_write_unavailable report_id={}", reportId); }
        }
        LOG.debug("published_body_cache_miss report_id={}", reportId);
        return body;
    }
    private Map<String, Object> decode(String raw, UUID reportId, String hash, String schema) {
        if (!Json.hash(raw).equals(hash)) return null;
        try {
            Map<String, Object> body = Json.object(raw);
            return reportId.toString().equals(body.get("reportVersionId")) && schema.equals(body.get("schemaVersion")) ? body : null;
        } catch (RuntimeException e) { return null; }
    }
}
