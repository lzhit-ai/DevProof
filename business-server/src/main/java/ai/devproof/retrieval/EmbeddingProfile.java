package ai.devproof.retrieval;

import ai.devproof.infrastructure.ApiProblem;
import java.util.Map;
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Nonsecret query-model identity, frozen into each newly created verification task. */
@Component
public class EmbeddingProfile {
    private final Map<String,Object> body;
    public EmbeddingProfile(@Value("${EMBEDDING_PROVIDER:dashscope}") String provider,
        @Value("${EMBEDDING_MODEL:text-embedding-v4}") String model,
        @Value("${EMBEDDING_BASE_URL:https://dashscope.aliyuncs.com/compatible-mode/v1}") String base,
        @Value("${EMBEDDING_DIMENSIONS:768}") int dimensions) {
        if(provider.isBlank() || model.isBlank() || dimensions<1 || dimensions>8192)throw new IllegalArgumentException("Invalid embedding configuration");
        URI url=URI.create(base);
        if(!"https".equalsIgnoreCase(url.getScheme()) || url.getHost()==null || url.getUserInfo()!=null || url.getQuery()!=null || url.getFragment()!=null)
            throw new IllegalArgumentException("Embedding address must be a nonsecret HTTPS endpoint");
        body=Map.of("provider",provider,"model",model,"baseUrl",base.replaceAll("/+$",""),"dimensions",dimensions);
    }
    public Map<String,Object> body() { return body; }
    public static String indexVersion(Map<String,Object> body) {
        if(!(body.get("provider") instanceof String provider) || !(body.get("model") instanceof String model)
            || !(body.get("baseUrl") instanceof String) || !(body.get("dimensions") instanceof Number dimensions))
            throw new ApiProblem(409,"INPUT_STALE","任务没有有效的冻结检索模型配置");
        return "knowledge-extraction-v1|embedding:"+provider+":"+model+":d"+dimensions.intValue();
    }
}
