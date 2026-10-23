package ai.devproof.source;

import ai.devproof.infrastructure.*;
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.function.BooleanSupplier;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Bounded provider reads. Repository text cannot choose a host, redirect or credential. */
@Component
public class GitHubSourceClient {
    private static final int MAX_PAGES=50;
    private static final Pattern NEXT=Pattern.compile("<([^>]+)>;\\s*rel=\"next\"",Pattern.CASE_INSENSITIVE);
    private final int timeout,limit;
    private final Set<String> credentialRefs;
    public record Payload(List<Map<String,Object>> issues,List<Map<String,Object>> pullRequests,List<Map<String,Object>> milestones,boolean truncated,int pageCount,Map<String,Object> cursor) {}
    public record Timeline(List<Map<String,Object>> events,boolean truncated,int pageCount) {}
    public record Batch(Payload payload,Instant retryAt) {}
    private record Page(List<Map<String,Object>> items,boolean truncated,int count,Map<String,String> cursor) {}
    private record Response(Object body,String link,Instant retryAt) {}
    private record Target(String path,Map<String,String> query) {}
    public static class RateLimited extends ApiProblem {
        public final Instant retryAt;
        public final boolean quotaReset;
        public RateLimited(Instant retryAt) { this(retryAt,true); }
        public RateLimited(Instant retryAt,boolean quotaReset) { super(503,"SOURCE_RATE_LIMITED","GitHub 读取额度受限，已保存进度并等待恢复"); this.retryAt=retryAt; this.quotaReset=quotaReset; }
    }
    public static class SyncFailure extends ApiProblem {
        public final int pageCount;
        public final Map<String,Object> cursor;
        public SyncFailure(ApiProblem cause,int pages,Map<String,Object> cursor) { super(cause.status,cause.code,cause.getMessage()); this.pageCount=pages; this.cursor=cursor; }
    }
    public GitHubSourceClient(@Value("${GITHUB_SYNC_TIMEOUT_SECONDS:15}") int timeout,@Value("${GITHUB_SYNC_RESPONSE_LIMIT_BYTES:2097152}") int limit,
            @Value("${GITHUB_SOURCE_SECRET_REFS:GITHUB_SOURCE_TOKEN}") String refs) {
        if(timeout<1 || timeout>30 || limit<65536 || limit>8388608)throw new IllegalArgumentException("Invalid GitHub source bounds");
        this.timeout=timeout; this.limit=limit; credentialRefs=new HashSet<>(); for(String ref:refs.split(","))if(!ref.isBlank())credentialRefs.add(ref.trim());
    }
    public static Map<String,Object> initialCursor(String slug) { return start(slug,"pullRequests"); }
    public static boolean resumable(Map<String,Object> cursor) {
        return cursor.get("version") instanceof Number version && version.intValue()==1
            && Set.of("pullRequests","issues","milestones").contains(Objects.toString(cursor.get("stage"),""));
    }
    /** One response per checkpoint: a later provider failure cannot discard accepted pages. */
    @SuppressWarnings("unchecked") public Batch fetchPage(String slug,String apiBase,String ref,Map<String,Object> cursor,BooleanSupplier alive) {
        validate(slug,apiBase);
        if(!resumable(cursor) || !(cursor.get("query") instanceof Map<?,?> raw))throw invalid("GitHub 同步进度无效");
        String stage=(String)cursor.get("stage"),suffix=suffix(stage);
        Map<String,String> query=new LinkedHashMap<>();
        for(var entry:raw.entrySet()) {
            if(!(entry.getKey() instanceof String key) || !(entry.getValue() instanceof String value))throw invalid("GitHub 同步进度无效");
            query.put(key,value);
        }
        Target target=next("https://api.github.com"+Objects.toString(cursor.get("path"),"")+"?"+encode(query),slug,suffix);
        Response response=get(target.path(),target.query(),ref,alive);
        if(!(response.body() instanceof List<?> list) || list.stream().anyMatch(item->!(item instanceof Map<?,?>)))throw invalid("GitHub 来源返回格式无效");
        List<Map<String,Object>> items=list.stream().map(item->(Map<String,Object>)item).toList();
        var match=NEXT.matcher(Objects.toString(response.link(),""));
        Map<String,Object> continuation=match.find()?checkpoint(stage,next(match.group(1),slug,suffix)):
            stage.equals("pullRequests")?start(slug,"issues"):stage.equals("issues")?start(slug,"milestones"):Map.of();
        List<Map<String,Object>> issues=stage.equals("issues")?items.stream().filter(item->!(item.get("pull_request") instanceof Map<?,?>)).toList():List.of();
        return new Batch(new Payload(issues,stage.equals("pullRequests")?items:List.of(),stage.equals("milestones")?items:List.of(),!continuation.isEmpty(),1,continuation),response.retryAt());
    }
    private static Map<String,Object> start(String slug,String stage) {
        Map<String,String> query=new LinkedHashMap<>(Map.of("state","all","per_page","100"));
        if(!stage.equals("milestones")) { query.put("sort","updated"); query.put("direction","desc"); }
        return checkpoint(stage,new Target("/repos/"+slug+suffix(stage),query));
    }
    private static String suffix(String stage) {
        return switch(stage) { case "pullRequests"->"/pulls"; case "issues"->"/issues"; case "milestones"->"/milestones"; default->throw new ApiProblem(503,"SOURCE_RESPONSE_INVALID","GitHub 同步进度无效"); };
    }
    private static Map<String,Object> checkpoint(String stage,Target target) {
        return Map.of("version",1,"stage",stage,"path",target.path(),"query",target.query());
    }
    private String encode(Map<String,String> query) {
        return query.entrySet().stream().map(entry->URLEncoder.encode(entry.getKey(),StandardCharsets.UTF_8)+"="+URLEncoder.encode(entry.getValue(),StandardCharsets.UTF_8)).collect(java.util.stream.Collectors.joining("&"));
    }
    public Timeline issueTimeline(String slug,String apiBase,String ref,String number,BooleanSupplier alive) {
        validate(slug,apiBase); if(number==null || !number.matches("[0-9]+"))throw invalid("GitHub Issue 编号无效");
        Page page=pages(slug,"/issues/"+number+"/timeline",Map.of(),ref,alive);
        return new Timeline(page.items(),page.truncated(),page.count());
    }
    @SuppressWarnings("unchecked") private Page pages(String slug,String suffix,Map<String,String> query,String ref,BooleanSupplier alive) {
        List<Map<String,Object>> items=new ArrayList<>(); Map<String,String> current=new LinkedHashMap<>(query); current.put("per_page","100"); String path="/repos/"+slug+suffix;
        for(int page=1;page<=MAX_PAGES;page++) {
            Response response;
            try { response=get(path,current,ref,alive); }
            catch(ApiProblem e) { throw new SyncFailure(e,page-1,new LinkedHashMap<>(cursor(current))); }
            if(!(response.body() instanceof List<?> list) || list.stream().anyMatch(item->!(item instanceof Map<?,?>)))throw invalid("GitHub 来源返回格式无效");
            for(Object value:list)items.add((Map<String,Object>)value);
            var match=NEXT.matcher(Objects.toString(response.link(),"")); if(!match.find())return new Page(items,false,page,Map.of());
            Target next=next(match.group(1),slug,suffix); path=next.path(); current=next.query();
        }
        return new Page(items,true,MAX_PAGES,cursor(current));
    }
    private Response get(String path,Map<String,String> query,String ref,BooleanSupplier alive) {
        check(alive); HttpURLConnection connection=null;
        try {
            connection=(HttpURLConnection)URI.create("https://api.github.com"+path+"?"+encode(query)).toURL().openConnection();
            connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(timeout*1000); connection.setReadTimeout(timeout*1000);
            connection.setRequestProperty("Accept","application/vnd.github+json"); connection.setRequestProperty("User-Agent","DevProof-SourceSync/1.0"); connection.setRequestProperty("X-GitHub-Api-Version","2022-11-28");
            if(ref!=null) {
                if(!credentialRefs.contains(ref))throw new ApiProblem(403,"SOURCE_SECRET_FORBIDDEN","该 GitHub 来源密钥引用未授权给业务服务");
                String secret=System.getenv(ref); if(secret==null || secret.isBlank())throw new ApiProblem(503,"SOURCE_SECRET_UNAVAILABLE","服务端未配置 GitHub 来源所需密钥");
                connection.setRequestProperty("Authorization","Bearer "+secret);
            }
            int status=connection.getResponseCode();
            if(status<200 || status>=300) {
                String message="";
                if(status==403 && connection.getErrorStream()!=null)try(var input=connection.getErrorStream()) { message=new String(input.readNBytes(4096),StandardCharsets.UTF_8).toLowerCase(Locale.ROOT); }
                if(status==429 || status==403 && ("0".equals(connection.getHeaderField("X-RateLimit-Remaining")) || connection.getHeaderField("Retry-After")!=null || message.contains("rate limit")))
                    throw new RateLimited(retryAt(connection.getHeaderField("Retry-After"),connection.getHeaderField("X-RateLimit-Reset"),Instant.now()),"0".equals(connection.getHeaderField("X-RateLimit-Remaining")) && connection.getHeaderField("X-RateLimit-Reset")!=null);
                throw new ApiProblem(503,status>=500?"SOURCE_UNAVAILABLE":status==401?"SOURCE_UNAUTHORIZED":status==403?"SOURCE_FORBIDDEN":status==404?"SOURCE_NOT_FOUND":"SOURCE_REJECTED","GitHub 来源返回 HTTP "+status);
            }
            if(connection.getContentLengthLong()>limit)throw new ApiProblem(503,"SOURCE_RESPONSE_TOO_LARGE","GitHub 来源响应超过允许大小");
            byte[] bytes; long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(timeout);
            try(var input=connection.getInputStream();var output=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[8192]; int count;
                while((count=input.read(buffer,0,Math.min(buffer.length,limit+1-output.size())))!=-1) {
                    check(alive); if(System.nanoTime()>=deadline)throw new SocketTimeoutException(); output.write(buffer,0,count); if(output.size()>limit)break;
                }
                bytes=output.toByteArray();
            }
            if(bytes.length>limit)throw new ApiProblem(503,"SOURCE_RESPONSE_TOO_LARGE","GitHub 来源响应超过允许大小");
            String body=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
            Object decoded; try { decoded=Json.read(body); } catch(RuntimeException e) { throw invalid("GitHub 来源不是有效 JSON"); }
            Instant retry="0".equals(connection.getHeaderField("X-RateLimit-Remaining"))?retryAt(connection.getHeaderField("Retry-After"),connection.getHeaderField("X-RateLimit-Reset"),Instant.now()):null;
            return new Response(decoded,connection.getHeaderField("Link"),retry);
        } catch(CharacterCodingException e) { throw invalid("GitHub 来源不是 UTF-8 JSON"); }
        catch(IOException e) { throw new ApiProblem(503,"SOURCE_UNAVAILABLE","GitHub 来源当前不可用或读取超时"); }
        finally { if(connection!=null)connection.disconnect(); }
    }
    static Instant retryAt(String retryAfter,String reset,Instant now) {
        Instant result=now;
        if(retryAfter!=null)try {
            Instant candidate;
            try { candidate=now.plusSeconds(Long.parseLong(retryAfter.trim())); }
            catch(NumberFormatException e) { candidate=ZonedDateTime.parse(retryAfter,DateTimeFormatter.RFC_1123_DATE_TIME).toInstant(); }
            if(candidate.isAfter(result))result=candidate;
        } catch(DateTimeException | ArithmeticException ignored) {}
        if(reset!=null)try { Instant candidate=Instant.ofEpochSecond(Long.parseLong(reset.trim())); if(candidate.isAfter(result))result=candidate; }
        catch(DateTimeException | NumberFormatException ignored) {}
        return result.equals(now)?now.plusSeconds(60):result.plusSeconds(2);
    }
    private Target next(String raw,String slug,String suffix) {
        try {
            URI uri=URI.create(raw);
            if(!"https".equals(uri.getScheme()) || !"api.github.com".equals(uri.getHost()) || uri.getUserInfo()!=null || (uri.getPort()!=-1 && uri.getPort()!=443) || uri.getFragment()!=null)throw invalid("GitHub 分页链接不属于受控 API 主机");
            if(!uri.getPath().equals("/repos/"+slug+suffix) && !uri.getPath().matches("/repositories/[0-9]+"+Pattern.quote(suffix)))throw invalid("GitHub 分页链接超出当前来源范围");
            Map<String,String> query=new LinkedHashMap<>();
            if(uri.getRawQuery()!=null)for(String part:uri.getRawQuery().split("&")) { String[] pair=part.split("=",2); query.put(URLDecoder.decode(pair[0],StandardCharsets.UTF_8),pair.length==2?URLDecoder.decode(pair[1],StandardCharsets.UTF_8):""); }
            if(query.isEmpty())throw invalid("GitHub 分页链接缺少参数"); return new Target(uri.getPath(),query);
        } catch(IllegalArgumentException e) { throw invalid("GitHub 分页链接无效"); }
    }
    private void validate(String slug,String base) {
        if(slug==null || !slug.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"))throw new ApiProblem(422,"SOURCE_CONNECTION_INVALID","GitHub 仓库标识无效");
        if(!Set.of("https://api.github.com","https://api.github.com/").contains(base))throw new ApiProblem(422,"SOURCE_CONNECTION_INVALID","GitHub 来源仅允许使用 https://api.github.com");
    }
    private Map<String,String> cursor(Map<String,String> query) { Map<String,String> result=new LinkedHashMap<>(); query.forEach((key,value)->{if(Set.of("page","after","before","since").contains(key))result.put(key,value);}); return result; }
    private void check(BooleanSupplier alive) { if(!alive.getAsBoolean() || Thread.currentThread().isInterrupted())throw new ApiProblem(409,"SOURCE_SYNC_LEASE_EXPIRED","来源同步执行已停止或被替换"); }
    private ApiProblem invalid(String message) { return new ApiProblem(503,"SOURCE_RESPONSE_INVALID",message); }
}
