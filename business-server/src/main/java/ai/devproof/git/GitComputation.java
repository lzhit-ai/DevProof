package ai.devproof.git;

import ai.devproof.infrastructure.*;
import ai.devproof.knowledge.ComputeClient;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.stereotype.Component;

/** Authenticated read-only products, verified before any formal snapshot is saved. */
@Component
public class GitComputation {
    public record Range(String baseRef,String targetRef,String mode,List<String> includes,List<String> excludes) {}
    public record Frozen(String base,String target,String merge,String effective,String diffHash,byte[] diff,
                         String bundleJson,Map<String,Object> coverage) {}
    private final ComputeClient compute;
    public GitComputation(ComputeClient compute) { this.compute=compute; }
    public Frozen capture(UUID project,UUID repository,String url,String credential,Range range) {
        try { return calculate(project,repository,url,credential,range); }
        catch(ApiProblem e) { throw e; }
        catch(RuntimeException e) { throw invalid(); }
    }
    private Frozen calculate(UUID project,UUID repository,String url,String credential,Range range) {
        var response=compute.gitConfiguration(); var configuration=object(response.get("configuration"));
        String configurationHash=text(response,"configurationHash");
        require("git-compute-configuration-v1".equals(configuration.get("schemaVersion"))
            && "git-capture-v4".equals(configuration.get("captureVersion")) && Json.hash(Json.canonical(configuration)).equals(configurationHash));
        require(text(configuration,"syntaxVersion").matches("tree-sitter-language-pack:[0-9][0-9A-Za-z.+-]{0,63}\\|tree-sitter:[0-9][0-9A-Za-z.+-]{0,63}")
            && List.of("java","python","javascript","typescript","tsx").equals(configuration.get("syntaxLanguages")));
        int timeout=number(configuration,"timeoutSeconds",10,600),maxDiff=number(configuration,"diffMaxBytes",65536,67108864);
        number(configuration,"commandTimeoutSeconds",5,300); number(configuration,"sshConnectTimeoutSeconds",1,60);
        number(configuration,"treeMaxBytes",65536,33554432); number(configuration,"contextMaxFileBytes",4096,2097152);
        number(configuration,"contextMaxTotalBytes",65536,8388608); number(configuration,"contextMaxRelatedSymbols",1,50);
        Map<String,Object> request=new LinkedHashMap<>();
        request.put("schemaVersion","git-capture-request-v1"); request.put("configurationHash",configurationHash);
        request.put("projectId",project.toString()); request.put("repositoryId",repository.toString());
        request.put("repositoryUrl",url); request.put("credentialRef",credential);
        request.put("baseRef",range.baseRef()); request.put("targetRef",range.targetRef()); request.put("diffMode",range.mode());
        request.put("includePaths",range.includes()); request.put("excludePaths",range.excludes());
        byte[] raw=Json.canonical(request).getBytes(StandardCharsets.UTF_8);
        var result=compute.captureGit(raw,timeout+10);
        require("git-capture-result-v1".equals(result.get("schemaVersion")) && Json.hash(raw).equals(result.get("requestHash"))
            && configurationHash.equals(result.get("configurationHash")));
        String base=sha(result,"baseSha"),target=sha(result,"targetSha"),merge=sha(result,"mergeBaseSha"),effective=sha(result,"effectiveBaseSha");
        require(effective.equals("TWO_DOT".equals(range.mode())?base:merge));
        byte[] diff;
        try { diff=Base64.getDecoder().decode(text(result,"diffBase64")); } catch(IllegalArgumentException e) { throw invalid(); }
        require(diff.length>0 && diff.length<=maxDiff && Json.hash(diff).equals(text(result,"diffHash")));
        String bundleJson=text(result,"bundleJson"); require(Json.hash(bundleJson).equals(text(result,"bundleHash")));
        var bundle=Json.object(bundleJson); require("code-change-bundle-v2".equals(bundle.get("schemaVersion")));
        var coverage=object(result.get("coverage"));
        require((effective+".."+target).equals(coverage.get("comparison")) && range.includes().equals(coverage.get("includePaths"))
            && range.excludes().equals(coverage.get("excludePaths")) && object(bundle.get("coverage")).equals(coverage.get("codeReview")));
        String normalizedDiff=new String(diff,StandardCharsets.UTF_8).replaceAll("\\r\\n|[\\n\\r\\u000b\\f\\u001c\\u001d\\u001e\\u0085\\u2028\\u2029]","\n");
        for(Object rawFile:list(bundle.get("files"))) {
            var file=object(rawFile); text(file,"path");
            String patch=text(file,"patch"); require(patch.startsWith("diff --git ") && normalizedDiff.contains(patch)); list(file.get("hunks"));
        }
        for(Object rawContext:list(bundle.get("contexts"))) {
            var context=object(rawContext);
            require(target.equals(context.get("commitSha")) && "CONTEXT_ONLY".equals(context.get("evidenceRole"))
                && Json.hash(text(context,"content")).equals(context.get("contentHash")));
        }
        for(Object candidate:list(bundle.get("contextCandidates")))require(target.equals(object(candidate).get("targetSha")));
        coverage=new LinkedHashMap<>(coverage); coverage.put("captureConfiguration",configuration);
        coverage.put("configurationHash",configurationHash); coverage.put("requestHash",Json.hash(raw));
        return new Frozen(base,target,merge,effective,text(result,"diffHash"),diff,bundleJson,Collections.unmodifiableMap(coverage));
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object raw) { require(raw instanceof Map<?,?>); return (Map<String,Object>)raw; }
    private static List<?> list(Object raw) { require(raw instanceof List<?>); return (List<?>)raw; }
    private static String text(Map<String,Object> map,String key) { require(map.get(key) instanceof String); return (String)map.get(key); }
    private static String sha(Map<String,Object> map,String key) { String value=text(map,key); require(value.matches("(?:[a-f0-9]{40}|[a-f0-9]{64})")); return value; }
    private static int number(Map<String,Object> map,String key,int min,int max) { Object raw=map.get(key); require(raw instanceof Integer || raw instanceof Long); long value=((Number)raw).longValue(); require(value>=min && value<=max); return (int)value; }
    private static void require(boolean valid) { if(!valid)throw invalid(); }
    private static ApiProblem invalid() { return new ApiProblem(502,"GIT_COMPUTE_CONTRACT_INVALID","Git 采集结果不符合请求范围和制品契约"); }
}
