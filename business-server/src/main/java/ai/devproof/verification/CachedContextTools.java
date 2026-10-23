package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/** Reads only registered candidates at the frozen SHA; no fetch, remote URL or credentials. */
@Service
public class CachedContextTools {
    private final VerificationToolScope scope;
    private final VerificationToolStore store;
    private final VerificationMaterials materials;
    private final VerificationExecutionMapper data;
    private final JdbcTemplate jdbc;
    private final Path artifacts,cache;
    private record Selection(Map<String,Object> run,List<Map<String,Object>> requests,Map<String,Map<String,Object>> candidates,String sha) {}
    public CachedContextTools(VerificationToolScope scope,VerificationToolStore store,VerificationMaterials materials,VerificationExecutionMapper data,JdbcTemplate jdbc,
            @Value("${ARTIFACT_ROOT:/artifacts}") String artifacts,@Value("${devproof.repository-cache-root:/repository-cache}") String cache) {
        this.scope=scope; this.store=store; this.materials=materials; this.data=data; this.jdbc=jdbc;
        this.artifacts=Path.of(artifacts).toAbsolutePath().normalize(); this.cache=Path.of(cache).toAbsolutePath().normalize();
    }
    public Object read(Map<String,Object> payload,Map<String,Object> arguments) {
        if(!arguments.keySet().equals(Set.of("requests")))throw invalid();
        Selection selected=select(payload,arguments.get("requests"));
        Map<String,Object> recorded=store.context(payload); if(recorded!=null)return Map.of("recorded",recorded);
        return sources(payload,selected);
    }
    public Object record(Map<String,Object> payload,Map<String,Object> arguments) {
        if(!arguments.keySet().equals(Set.of("requests","contexts","skipped")))throw invalid();
        Selection selected=select(payload,arguments.get("requests"));
        Map<String,Object> recorded=store.context(payload); if(recorded!=null)return recorded;
        Map<String,Object> actual=sources(payload,selected); Map<String,Map<String,Object>> byCandidate=new HashMap<>();
        for(Map<String,Object> source:VerificationMaterials.objects(actual.get("sources")))byCandidate.put((String)source.get("candidateId"),source);
        List<Map<String,Object>> proposed=VerificationMaterials.objects(arguments.get("contexts"));
        if(proposed.size()>selected.requests().size())throw invalid();
        Set<String> seen=new HashSet<>(); List<Map<String,Object>> contexts=new ArrayList<>();
        for(Map<String,Object> item:proposed) {
            if(!item.keySet().equals(Set.of("candidateId","symbol","symbolKind","startLine","endLine","content")))throw invalid();
            String candidateId=string(item,"candidateId",64); Map<String,Object> source=byCandidate.get(candidateId), candidate=selected.candidates().get(candidateId);
            if(source==null || candidate==null || !seen.add(candidateId) || !candidate.get("symbol").equals(item.get("symbol")))throw invalid();
            int start=number(item,"startLine"),end=number(item,"endLine"); String content=string(item,"content",scope.limit(payload,"contextMaxFileBytes"));
            String raw=(String)source.get("source"); String[] lines=raw.replace("\r\n","\n").split("\n",-1);
            if(start<1 || end<start || end>lines.length)throw invalid();
            String window=String.join("\n",Arrays.copyOfRange(lines,start-1,end));
            if(!window.contains(content.replace("\r\n","\n")))throw new ApiProblem(422,"CONTEXT_SOURCE_INVALID","补充上下文与冻结文件行范围不一致");
            Map<String,Object> request=selected.requests().stream().filter(entry->candidateId.equals(entry.get("candidateId"))).findFirst().orElseThrow(this::invalid);
            Map<String,Object> context=new LinkedHashMap<>();
            context.put("contextId","ctx-supplement-"+Json.hash(candidateId+content).substring(7,27)); context.put("path",candidate.get("path")); context.put("commitSha",selected.sha());
            context.put("symbol",candidate.get("symbol")); context.put("symbolKind",string(item,"symbolKind",128)); context.put("kind","SYMBOL"); context.put("relation","SUPPLEMENTAL_DIRECT_IMPORT");
            context.put("startLine",start); context.put("endLine",end); context.put("content",content); context.put("contentHash",Json.hash(content)); context.put("evidenceRole","CONTEXT_ONLY");
            context.put("requestedForClaimId",request.get("claimId")); context.put("requestReason",request.get("reason")); contexts.add(context);
        }
        List<Map<String,Object>> skipped=new ArrayList<>(VerificationMaterials.objects(actual.get("skipped")));
        for(Map<String,Object> item:VerificationMaterials.objects(arguments.get("skipped"))) {
            if(!item.keySet().equals(Set.of("candidateId","reasonCode")) || !byCandidate.containsKey(item.get("candidateId")) || !Set.of("SYMBOL_DEFINITION_NOT_FOUND","PARSER_UNAVAILABLE").contains(item.get("reasonCode")))throw invalid();
            skipped.add(item);
        }
        if(skipped.size()>selected.requests().size())throw invalid();
        return store.recordContext(payload,Json.hash(Json.write(selected.requests())),Map.of("schemaVersion","run-context-v2","targetSha",selected.sha(),"requests",selected.requests(),"contexts",contexts,"skipped",skipped));
    }
    private Selection select(Map<String,Object> payload,Object raw) {
        Map<String,Object> run=scope.require(payload); List<Map<String,Object>> requests=VerificationMaterials.objects(raw);
        if(requests.isEmpty() || requests.size()>scope.limit(payload,"contextMaxSupplementRequests"))throw invalid();
        UUID snapshot=(UUID)run.get("snapshot_id"), project=(UUID)run.get("project_id"); VerificationMaterials.Capture capture=materials.capture(snapshot,project);
        Map<String,Map<String,Object>> candidates=new HashMap<>();
        for(Map<String,Object> candidate:VerificationMaterials.objects(capture.bundle().getOrDefault("contextCandidates",List.of())))candidates.put((String)candidate.get("candidateId"),candidate);
        Set<String> claims=new HashSet<>(); data.claims((UUID)run.get("id")).forEach(row->claims.add(row.get("id").toString()));
        String sha=(String)capture.git().get("target_sha"); if(sha==null || !sha.matches("(?:[0-9a-f]{40}|[0-9a-f]{64})"))throw invalid();
        Set<String> seen=new HashSet<>(); List<Map<String,Object>> selected=new ArrayList<>();
        for(Map<String,Object> request:requests) {
            if(!request.keySet().equals(Set.of("candidateId","claimId","reason")))throw invalid();
            String id=string(request,"candidateId",64); Map<String,Object> candidate=candidates.get(id);
            if(candidate==null || !sha.equals(candidate.get("targetSha")) || !claims.contains(request.get("claimId")))throw invalid();
            string(request,"reason",1000); String path=string(candidate,"path",4096);
            if(path.startsWith("/") || path.indexOf('\\')>=0 || path.indexOf('\0')>=0 || Arrays.stream(path.split("/",-1)).anyMatch(part->part.equals("..") || part.equals(".") || part.isEmpty()))throw invalid();
            if(seen.add(id))selected.add(request);
        }
        return new Selection(run,selected,candidates,sha);
    }
    private Map<String,Object> sources(Map<String,Object> payload,Selection selected) {
        Map<String,Object> git=data.git((UUID)selected.run().get("snapshot_id"));
        String display=jdbc.queryForObject("SELECT display_url FROM git_repositories WHERE id=? AND project_id=?",String.class,git.get("repository_id"),selected.run().get("project_id"));
        Path directory=localCache((UUID)selected.run().get("project_id"),(UUID)git.get("repository_id"),display);
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(20); int total=0;
        List<Map<String,Object>> sources=new ArrayList<>(),skipped=new ArrayList<>(); Map<String,byte[]> blobs=new HashMap<>();
        for(Map<String,Object> request:selected.requests()) {
            String id=(String)request.get("candidateId"); Map<String,Object> candidate=selected.candidates().get(id);
            try {
                String path=(String)candidate.get("path"); byte[] bytes=blobs.get(path);
                if(bytes==null) {
                    bytes=GitProcess.run(directory,GitProcess.localEnvironment(),deadline,scope.limit(payload,"contextMaxFileBytes"),"cat-file","blob",selected.sha()+":"+path);
                    if(total+bytes.length>scope.limit(payload,"contextMaxTotalBytes")) { skipped.add(Map.of("candidateId",id,"reasonCode","GIT_CONTEXT_BUDGET_EXCEEDED")); continue; }
                    total+=bytes.length; blobs.put(path,bytes);
                }
                sources.add(Map.of("candidateId",id,"path",candidate.get("path"),"symbol",candidate.get("symbol"),"source",new String(bytes,StandardCharsets.UTF_8),"sourceHash",Json.hash(bytes),"commitSha",selected.sha(),"evidenceRole","CONTEXT_ONLY"));
            } catch(IOException|ApiProblem e) { skipped.add(Map.of("candidateId",id,"reasonCode",e instanceof ApiProblem problem?problem.code:"GIT_CONTEXT_UNAVAILABLE")); }
        }
        if(sources.isEmpty())throw new ApiProblem(409,"GIT_CONTEXT_UNAVAILABLE","本地冻结上下文当前不可读取");
        return Map.of("sources",sources,"skipped",skipped);
    }
    private Path localCache(UUID project,UUID repository,String display) {
        List<Path> candidates=List.of(cache.resolve(project.toString()).resolve(repository.toString()).resolve("repository.git"),artifacts.resolve("repositories").resolve(Json.hash(display).substring(7)).resolve(".git"));
        for(Path candidate:candidates)try {
            Path root=(candidate.startsWith(cache)?cache:artifacts).toRealPath(), directory=candidate.toRealPath();
            if(directory.startsWith(root) && Files.isRegularFile(directory.resolve("HEAD")))return directory;
        } catch(IOException ignored) {}
        throw new ApiProblem(409,"GIT_CONTEXT_UNAVAILABLE","本地仓库缓存不存在，分析阶段不能重新抓取");
    }
    private String string(Map<String,Object> raw,String key,int max) { if(!(raw.get(key) instanceof String value) || value.isEmpty() || value.codePointCount(0,value.length())>max)throw invalid(); return value; }
    private int number(Map<String,Object> raw,String key) { if(!(raw.get(key) instanceof Number value) || value.doubleValue()!=value.intValue())throw invalid(); return value.intValue(); }
    private ApiProblem invalid() { return new ApiProblem(422,"TOOL_INPUT_INVALID","补充上下文必须来自本任务冻结候选、主张和原文范围"); }
}
