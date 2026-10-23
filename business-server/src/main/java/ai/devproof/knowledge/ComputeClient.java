package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.Flow;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** A stateless computation boundary: Java chooses bytes/configuration and validates every product. */
@Component
public class ComputeClient {
    public record Configuration(Map<String,Object> body,String hash,List<String> extensions,
                                Boolean embeddingConfigured,Boolean mineruConfigured) {
        public int dimensions() { return integer(object(body.get("embedding")),"dimensions",1,8192); }
        public String parserVersion() { return text(object(body.get("parser")),"parserVersion"); }
        public String indexVersion() {
            var embedding=object(body.get("embedding"));
            return parserVersion()+"|embedding:"+text(embedding,"provider")+":"+text(embedding,"model")+":d"+dimensions();
        }
    }
    public record Inspection(String contentHash,String mediaType,int byteSize) {}
    public record Chunk(int index,String content,String hash,Map<String,Object> locator,List<Double> vector) {}
    public record Extraction(String contentHash,String configurationHash,String mediaType,String parserVersion,
                             String normalizedText,String normalizedTextHash,Map<String,Object> metadata,
                             String indexVersion,String indexingStatus,String indexingError,List<Chunk> chunks) {}

    private final URI base;
    private final String token;
    private final int timeout,maxResult;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER).build();
    public ComputeClient(@Value("${COMPUTE_API_URL:http://agent-worker:8090}") String url,
                         @Value("${COMPUTE_SERVICE_TOKEN:}") String token,
                         @Value("${COMPUTE_TIMEOUT_SECONDS:1800}") int timeout,
                         @Value("${COMPUTE_RESULT_MAX_BYTES:268435456}") int maxResult) {
        base=URI.create(url);
        if(!Set.of("http","https").contains(base.getScheme()) || base.getHost()==null || base.getUserInfo()!=null
            || base.getQuery()!=null || base.getFragment()!=null || !Set.of("","/").contains(base.getPath()))
            throw new IllegalArgumentException("Invalid internal compute URL");
        if(timeout<60 || timeout>7200 || maxResult<1048576 || maxResult>1073741824)
            throw new IllegalArgumentException("Invalid compute limits");
        this.token=token; this.timeout=timeout; this.maxResult=maxResult;
    }
    public Configuration configuration() {
        Map<String,Object> response=request("/internal/v1/compute/configuration",null,Map.of(),65536,15);
        Map<String,Object> body=object(response.get("configuration"));
        require("compute-configuration-v1".equals(body.get("schemaVersion")));
        String hash=text(response,"configurationHash"); require(Json.hash(Json.canonical(body)).equals(hash));
        var parser=object(body.get("parser")); var embedding=object(body.get("embedding"));
        require("knowledge-extraction-v1".equals(text(parser,"parserVersion")));
        integer(embedding,"dimensions",1,8192); boundedText(embedding,"provider",64); boundedText(embedding,"model",255);
        text(embedding,"baseUrl"); text(parser,"mineruBaseUrl"); text(parser,"mineruModelVersion"); text(parser,"mineruLanguage");
        integer(parser,"mineruTimeoutSeconds",60,1800); integer(parser,"mineruPollIntervalSeconds",1,60);
        integer(parser,"mineruResultMaxBytes",1048576,134217728);
        integer(body,"sourceMaxBytes",1048576,524288000); integer(body,"resultMaxBytes",1048576,1073741824);
        integer(body,"timeoutSeconds",60,7200);
        List<String> extensions=list(response.get("supportedExtensions")).stream().map(value->{
            require(value instanceof String extension && extension.matches("\\.[a-z0-9]+")); return (String)value;
        }).toList();
        require(response.get("embeddingCredentialConfigured") instanceof Boolean && response.get("mineruCredentialConfigured") instanceof Boolean);
        return new Configuration(Collections.unmodifiableMap(body),hash,extensions,
            (Boolean)response.get("embeddingCredentialConfigured"),(Boolean)response.get("mineruCredentialConfigured"));
    }
    public Inspection inspect(byte[] bytes,String filename) {
        Map<String,Object> result=request("/internal/v1/compute/documents/inspect?filename="+encode(filename),bytes,Map.of(),65536,30);
        require("document-inspection-v1".equals(result.get("schemaVersion")));
        String hash=text(result,"contentHash"); require(Json.hash(bytes).equals(hash));
        int size=integer(result,"byteSize",1,524288000); require(size==bytes.length);
        return new Inspection(hash,text(result,"mediaType"),size);
    }
    public Map<String,Object> gitConfiguration() {
        return request("/internal/v1/compute/git/configuration",null,Map.of(),65536,15);
    }
    public Map<String,Object> captureGit(byte[] request,int seconds) {
        return request("/internal/v1/compute/git/capture",request,Map.of("Content-Type","application/json"),maxResult,seconds);
    }
    public Extraction extract(byte[] bytes,String filename,boolean forceOcr,String mediaType,Configuration configuration) {
        String contentHash=Json.hash(bytes);
        Map<String,Object> result=request("/internal/v1/compute/documents/extract?filename="+encode(filename)+"&forceOcr="+forceOcr,
            bytes,Map.of("X-Content-Hash",contentHash,"X-Compute-Configuration-Hash",configuration.hash()),maxResult,timeout);
        require("document-computation-v1".equals(result.get("schemaVersion")));
        require(contentHash.equals(result.get("contentHash")) && configuration.hash().equals(result.get("configurationHash"))
            && mediaType.equals(result.get("mediaType")) && configuration.parserVersion().equals(result.get("parserVersion"))
            && result.containsKey("ocrConfidence") && result.get("ocrConfidence")==null);
        String normalized=textAllowEmpty(result,"normalizedText"), normalizedHash=text(result,"normalizedTextHash");
        require(Json.hash(normalized).equals(normalizedHash));
        Map<String,Object> metadata=object(result.get("metadata")), indexing=object(result.get("indexing"));
        String status=text(indexing,"status"), error=indexing.get("code")==null?null:text(indexing,"code");
        require(Set.of("AVAILABLE","UNAVAILABLE").contains(status));
        boolean available="AVAILABLE".equals(status);
        require(available?error==null:error!=null && Set.of("MODEL_UNAVAILABLE","MODEL_NOT_CONFIGURED").contains(error));
        String index=text(result,"indexVersion");
        require(index.equals(available?configuration.indexVersion():configuration.parserVersion()+"|embedding:unavailable"));
        require(index.codePointCount(0,index.length())<=512);
        List<Chunk> chunks=validatedChunks(result.get("chunks"),normalized,available,configuration.dimensions());
        return new Extraction(contentHash,configuration.hash(),mediaType,configuration.parserVersion(),normalized,normalizedHash,
            Collections.unmodifiableMap(metadata),index,status,error,List.copyOf(chunks));
    }
    public List<List<Double>> embed(List<String> texts,Configuration configuration) {
        require(!texts.isEmpty());
        byte[] bytes=Json.canonical(Map.of("schemaVersion","embedding-batch-request-v1","configurationHash",configuration.hash(),"texts",texts)).getBytes(StandardCharsets.UTF_8);
        Map<String,Object> result=request("/internal/v1/compute/embeddings",bytes,Map.of("Content-Type","application/json"),maxResult,timeout);
        require("embedding-batch-result-v1".equals(result.get("schemaVersion")) && configuration.hash().equals(result.get("configurationHash")));
        var hashes=list(result.get("textHashes")); var vectors=list(result.get("vectors"));
        require(hashes.size()==texts.size() && vectors.size()==texts.size());
        List<List<Double>> output=new ArrayList<>();
        for(int i=0;i<texts.size();i++) {
            require(Json.hash(texts.get(i)).equals(hashes.get(i))); output.add(vector(vectors.get(i),configuration.dimensions()));
        }
        return List.copyOf(output);
    }
    public static Configuration frozen(String json,String hash) {
        Map<String,Object> body=Json.object(json);
        require(Json.hash(Json.canonical(body)).equals(hash) && "compute-configuration-v1".equals(body.get("schemaVersion")));
        return new Configuration(Collections.unmodifiableMap(body),hash,null,null,null);
    }
    public List<Chunk> rechunk(String normalized,Configuration configuration) {
        byte[] bytes=normalized.getBytes(StandardCharsets.UTF_8);
        Map<String,Object> result=request("/internal/v1/compute/documents/rechunk",bytes,
            Map.of("X-Content-Hash",Json.hash(bytes),"X-Compute-Configuration-Hash",configuration.hash()),maxResult,timeout);
        require("normalized-chunks-v1".equals(result.get("schemaVersion")) && Json.hash(bytes).equals(result.get("normalizedTextHash"))
            && configuration.hash().equals(result.get("configurationHash")));
        return validatedChunks(result.get("chunks"),normalized,false,configuration.dimensions());
    }
    private static List<Chunk> validatedChunks(Object rawChunks,String normalized,boolean available,int dimensions) {
        List<?> values=list(rawChunks); require(!values.isEmpty());
        List<Chunk> chunks=new ArrayList<>(); String locatorText=normalized.replace("\r\n","\n");
        String[] lines=normalized.split("\\r\\n|[\\n\\r\\u000b\\f\\u001c\\u001d\\u001e\\u0085\\u2028\\u2029]",-1);
        for(int i=0;i<values.size();i++) {
            var chunk=object(values.get(i)); require(integer(chunk,"chunkIndex",0,Integer.MAX_VALUE)==i);
            String content=text(chunk,"content"), hash=text(chunk,"textHash"); require(Json.hash(content).equals(hash));
            Map<String,Object> locator=object(chunk.get("locator"));
            if(locator.containsKey("charStart") || locator.containsKey("charEnd")) {
                int count=locatorText.codePointCount(0,locatorText.length());
                int start=integer(locator,"charStart",0,count),end=integer(locator,"charEnd",start,count);
                require(locatorText.substring(locatorText.offsetByCodePoints(0,start),locatorText.offsetByCodePoints(0,end)).equals(content));
            } else {
                int line=integer(locator,"line",1,lines.length); require(UnicodeText.strip(lines[line-1]).equals(content));
            }
            List<Double> vector=available?vector(chunk.get("embedding"),dimensions):null;
            if(!available)require(chunk.get("embedding")==null);
            chunks.add(new Chunk(i,content,hash,Collections.unmodifiableMap(locator),vector));
        }
        return List.copyOf(chunks);
    }
    private Map<String,Object> request(String path,byte[] bytes,Map<String,String> headers,int limit,int seconds) {
        if(token==null || token.length()<32)throw new ApiProblem(503,"COMPUTE_NOT_CONFIGURED","内部计算服务身份尚未配置");
        HttpRequest.Builder builder=HttpRequest.newBuilder(base.resolve(path)).timeout(Duration.ofSeconds(seconds))
            .header("Authorization","Bearer "+token).header("Accept","application/json");
        headers.forEach(builder::header);
        builder.method(bytes==null?"GET":"POST",bytes==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofByteArray(bytes));
        CompletableFuture<HttpResponse<byte[]>> pending=http.sendAsync(builder.build(),info->new BoundedBody(limit));
        try {
            HttpResponse<byte[]> response=pending.get(seconds,TimeUnit.SECONDS);
            Map<String,Object> result=object(Json.read(response.body()));
            if(response.statusCode()!=200) {
                String code=result.get("code") instanceof String value && value.matches("[A-Z][A-Z0-9_]{0,63}")?value:"COMPUTE_UNAVAILABLE";
                int status=Set.of(409,413,422).contains(response.statusCode())?response.statusCode():503;
                String message=switch(code) {
                    case "GIT_COMMAND_TIMEOUT", "GIT_CAPTURE_TIMEOUT" -> "读取仓库超时，请检查网络后重试";
                    case "GIT_COMMAND_FAILED" -> "无法读取仓库或提交，请检查仓库权限和代码范围";
                    case "GIT_DIFF_EMPTY" -> "指定范围没有可冻结的 Git Diff";
                    case "GIT_CREDENTIAL_NOT_CONFIGURED" -> "仓库凭据尚未配置，请在设置中检查仓库连接";
                    case "REPOSITORY_BUSY" -> "仓库正在读取，请稍后重试";
                    case "REPOSITORY_STORAGE_UNAVAILABLE" -> "仓库缓存不可读写，请检查服务存储配置";
                    default -> "计算未完成，请根据错误码检查实际输入、服务配置或提供方响应";
                };
                throw new ApiProblem(status,code,message);
            }
            return result;
        } catch(TimeoutException e) { pending.cancel(true); throw new ApiProblem(503,"COMPUTE_TIMEOUT","内部计算服务未在配置时间内完成"); }
        catch(InterruptedException e) { pending.cancel(true); Thread.currentThread().interrupt(); throw new ApiProblem(503,"COMPUTE_CANCELLED","内部计算调用已停止"); }
        catch(ExecutionException e) {
            if(e.getCause() instanceof ApiProblem error)throw error;
            throw new ApiProblem(503,"COMPUTE_UNAVAILABLE","内部计算服务连接或响应不可用");
        } catch(ApiProblem e) { throw e; }
        catch(RuntimeException e) { throw invalid(); }
    }
    private static List<Double> vector(Object value,int dimensions) {
        List<?> values=list(value); require(values.size()==dimensions); List<Double> result=new ArrayList<>(dimensions);
        for(Object number:values) { require(number instanceof Number && Double.isFinite(((Number)number).doubleValue())); result.add(((Number)number).doubleValue()); }
        return List.copyOf(result);
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object value) { require(value instanceof Map<?,?>); return (Map<String,Object>)value; }
    private static List<?> list(Object value) { require(value instanceof List<?>); return (List<?>)value; }
    private static String text(Map<String,Object> body,String key) { String value=textAllowEmpty(body,key); require(!value.isEmpty()); return value; }
    private static String textAllowEmpty(Map<String,Object> body,String key) { require(body.get(key) instanceof String); return (String)body.get(key); }
    private static void boundedText(Map<String,Object> body,String key,int max) { String value=text(body,key); require(value.codePointCount(0,value.length())<=max); }
    private static int integer(Map<String,Object> body,String key,int min,int max) {
        Object value=body.get(key); require(value instanceof Integer || value instanceof Long);
        long number=((Number)value).longValue(); require(number>=min && number<=max); return (int)number;
    }
    private static String encode(String value) { return URLEncoder.encode(value,StandardCharsets.UTF_8); }
    private static void require(boolean valid) { if(!valid)throw invalid(); }
    private static ApiProblem invalid() { return new ApiProblem(502,"COMPUTE_CONTRACT_INVALID","内部计算结果不符合冻结输入和约定结构"); }

    private static class BoundedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final int limit;
        private final ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        private final CompletableFuture<byte[]> result=new CompletableFuture<>();
        private Flow.Subscription subscription;
        BoundedBody(int limit) { this.limit=limit; }
        public CompletionStage<byte[]> getBody() { return result; }
        public void onSubscribe(Flow.Subscription value) { subscription=value; value.request(1); }
        public void onNext(List<ByteBuffer> parts) {
            for(ByteBuffer part:parts) {
                if((long)bytes.size()+part.remaining()>limit) { subscription.cancel(); result.completeExceptionally(new ApiProblem(502,"COMPUTE_RESULT_TOO_LARGE","内部计算结果超过配置的大小上限")); return; }
                byte[] piece=new byte[part.remaining()]; part.get(piece); bytes.writeBytes(piece);
            }
            subscription.request(1);
        }
        public void onError(Throwable error) { result.completeExceptionally(error); }
        public void onComplete() { result.complete(bytes.toByteArray()); }
    }
}
