package ai.devproof.planning;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import ai.devproof.project.ProjectAccess;
import java.net.URI;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RepositorySnapshotService {
    private final PlanningMapper data;
    private final ProjectAccess access;
    private final TransactionTemplate transactions;
    private final Path cacheRoot;
    private final Set<String> credentialRefs;
    private final int maxFileBytes, maxTotalBytes, maxFiles, timeoutSeconds;

    public RepositorySnapshotService(PlanningMapper data, ProjectAccess access, TransactionTemplate transactions,
            @Value("${devproof.repository-cache-root:/repository-cache}") String root,
            @Value("${devproof.git-credential-refs:GITHUB_SOURCE_TOKEN}") String refs,
            @Value("${devproof.repository-file-bytes:262144}") int maxFileBytes,
            @Value("${devproof.repository-total-bytes:2097152}") int maxTotalBytes,
            @Value("${devproof.repository-max-files:200}") int maxFiles,
            @Value("${devproof.repository-timeout-seconds:110}") int timeoutSeconds) {
        this.data=data; this.access=access; this.transactions=transactions; cacheRoot=Path.of(root).toAbsolutePath().normalize();
        credentialRefs=new HashSet<>(Arrays.asList(refs.split(",")));
        if (maxFileBytes<1024 || maxTotalBytes<maxFileBytes || maxFiles<1 || timeoutSeconds<5) throw new IllegalArgumentException("Invalid repository capture limits");
        this.maxFileBytes=maxFileBytes; this.maxTotalBytes=maxTotalBytes; this.maxFiles=maxFiles; this.timeoutSeconds=timeoutSeconds;
    }
    public List<Map<String,Object>> repositories(UUID projectId, UUID actorId) {
        access.require(projectId,actorId);
        return data.repositories(projectId).stream().map(row -> Map.<String,Object>of("id",row.get("id"),"display_url",row.get("display_url"),
                "credential_ref_configured",row.get("credential_ref")!=null)).toList();
    }
    public List<Map<String,Object>> list(UUID projectId, UUID actorId) { access.require(projectId,actorId); return data.snapshots(projectId); }

    public Map<String,Object> capture(UUID projectId, UUID repositoryId, String ref, UUID actorId) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN");
        Map<String,Object> repository=data.repository(projectId,repositoryId);
        if (repository==null) throw new ApiProblem(404,"RESOURCE_NOT_FOUND","仓库不存在或不属于当前项目");
        if (!ref.matches("[A-Za-z0-9_][A-Za-z0-9_./-]{0,254}") || ref.contains("..")) throw new ApiProblem(422,"GIT_REF_INVALID","请指定有效的分支、标签或完整提交 SHA");
        String url=githubUrl((String)repository.get("display_url"));
        Map<String,String> environment=gitEnvironment((String)repository.get("credential_ref"));
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(timeoutSeconds);
        Path directory=cacheRoot.resolve(projectId.toString()).resolve(repositoryId.toString());
        try {
            Files.createDirectories(directory);
            try (FileChannel channel=FileChannel.open(directory.resolve("capture.lock"),StandardOpenOption.CREATE,StandardOpenOption.WRITE);
                 FileLock lock=channel.tryLock()) {
                if (lock==null) throw new ApiProblem(409,"REPOSITORY_BUSY","仓库正在抓取，请稍后重试");
                Path bare=directory.resolve("repository.git");
                if (!Files.exists(bare.resolve("HEAD"))) git(null,environment,deadline,65536,"init","--bare",bare.toString());
                git(bare,environment,deadline,65536,"fetch","--no-tags","--",url,ref);
                String sha=new String(git(bare,environment,deadline,256,"rev-parse","--verify","FETCH_HEAD^{commit}"),StandardCharsets.UTF_8).trim();
                if (!sha.matches("(?:[0-9a-f]{40}|[0-9a-f]{64})")) throw new ApiProblem(409,"GIT_SHA_INVALID","Git 未返回完整提交 SHA");
                byte[] index=git(bare,environment,deadline,4*1024*1024,"ls-tree","-rlz","--full-tree",sha);
                List<Map<String,Object>> files=new ArrayList<>(), skipped=new ArrayList<>();
                List<String> entries=new ArrayList<>(Arrays.asList(new String(index,StandardCharsets.UTF_8).split("\u0000")));
                entries.sort(Comparator.comparingInt(this::priority));
                int used=0;
                for (String entry:entries) {
                    if (entry.isEmpty()) continue;
                    String[] parts=entry.split("\t",2), info=parts[0].trim().split("\\s+");
                    if (parts.length!=2 || info.length!=4) throw new ApiProblem(409,"GIT_TREE_INVALID","Git 文件索引格式无效");
                    String path=parts[1];
                    if (!info[0].startsWith("100") || !textPath(path)) { skipped.add(Map.of("path",path,"reason","UNSUPPORTED_OR_GENERATED")); continue; }
                    long size=Long.parseLong(info[3]);
                    if (size>maxFileBytes || used+size>maxTotalBytes || files.size()>=maxFiles) { skipped.add(Map.of("path",path,"reason","CAPTURE_BUDGET_EXHAUSTED")); continue; }
                    byte[] bytes=git(bare,environment,deadline,maxFileBytes,"cat-file","blob",sha+":"+path);
                    if (new String(bytes,StandardCharsets.ISO_8859_1).indexOf('\0')>=0) { skipped.add(Map.of("path",path,"reason","BINARY")); continue; }
                    String content;
                    try { content=StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(bytes)).toString(); }
                    catch (java.nio.charset.CharacterCodingException invalidText) { skipped.add(Map.of("path",path,"reason","NON_UTF8_TEXT")); continue; }
                    files.add(Map.of("path",path,"content",content,"lineCount",content.split("\n",-1).length,"contentHash",Json.hash(content)));
                    used+=bytes.length;
                }
                String body=Json.write(Map.of("schemaVersion","repository-snapshot-v1","repositoryId",repositoryId.toString(),"targetSha",sha,
                        "files",files,"coverage",Map.of("capturedFiles",files.size(),"capturedBytes",used,"skipped",skipped)));
                UUID id=UUID.randomUUID();
                // No database transaction is held while Git is fetching/reading.
                transactions.executeWithoutResult(status -> {
                    access.require(projectId,actorId,"SUBMITTER","ADMIN");
                    data.snapshot(id,projectId,repositoryId,sha,Json.hash(body),body,actorId);
                });
                return Map.of("id",id,"repository_id",repositoryId,"target_sha",sha,"content_hash",Json.hash(body),"coverage",Json.object(body).get("coverage"));
            }
        } catch (OverlappingFileLockException e) { throw new ApiProblem(409,"REPOSITORY_BUSY","仓库正在抓取，请稍后重试"); }
        catch (java.io.IOException e) { throw new ApiProblem(503,"REPOSITORY_STORAGE_UNAVAILABLE","仓库缓存不可写或 Git 未安装"); }
    }

    public Map<String,Object> load(UUID projectId, UUID id) {
        Map<String,Object> row=data.snapshotById(projectId,id);
        if (row==null) throw new ApiProblem(404,"RESOURCE_NOT_FOUND","仓库快照不存在或不属于当前项目");
        if (!Json.hash((String)row.get("body_json")).equals(row.get("content_hash"))) throw new ApiProblem(409,"INPUT_STALE","仓库快照摘要不一致");
        return row;
    }
    private String githubUrl(String raw) {
        try {
            URI uri=URI.create(raw);
            if (uri.getScheme()==null || !Set.of("https","ssh").contains(uri.getScheme()) || !"github.com".equalsIgnoreCase(uri.getHost()) || uri.getQuery()!=null || uri.getFragment()!=null
                    || (uri.getPort()!=-1 && uri.getPort()!=443) || (uri.getScheme().equals("https") && uri.getUserInfo()!=null)
                    || !uri.getPath().matches("/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?")) throw new IllegalArgumentException();
            return "https://github.com"+uri.getPath();
        } catch (IllegalArgumentException e) { throw new ApiProblem(422,"REPOSITORY_URL_UNSUPPORTED","规划抓取当前支持已登记的 GitHub HTTPS/SSH 仓库"); }
    }
    private Map<String,String> gitEnvironment(String ref) {
        Map<String,String> result=new HashMap<>();
        for (String key:List.of("PATH","SystemRoot","WINDIR","TEMP","TMP")) if (System.getenv(key)!=null) result.put(key,System.getenv(key));
        result.put("GIT_TERMINAL_PROMPT","0"); result.put("GIT_CONFIG_NOSYSTEM","1");
        result.put("GIT_CONFIG_GLOBAL",System.getProperty("os.name").startsWith("Windows")?"NUL":"/dev/null");
        if (ref!=null && !ref.isBlank()) {
            if (!credentialRefs.contains(ref) || !ref.matches("[A-Z][A-Z0-9_]{2,159}")) throw new ApiProblem(403,"CREDENTIAL_REF_FORBIDDEN","该仓库凭据引用未授权给 Java 服务");
            String value=System.getenv(ref);
            if (value==null || value.isBlank()) throw new ApiProblem(503,"GIT_CREDENTIAL_NOT_CONFIGURED","仓库凭据引用尚未配置");
            result.put("GIT_CONFIG_COUNT","1"); result.put("GIT_CONFIG_KEY_0","http.https://github.com/.extraheader");
            result.put("GIT_CONFIG_VALUE_0","Authorization: Basic "+Base64.getEncoder().encodeToString(("x-access-token:"+value).getBytes(StandardCharsets.UTF_8)));
        }
        return result;
    }
    private byte[] git(Path bare,Map<String,String> environment,long deadline,int limit,String... arguments) throws java.io.IOException {
        return ai.devproof.infrastructure.GitProcess.run(bare,environment,deadline,limit,arguments);
    }
    private boolean textPath(String path) {
        String lower=path.toLowerCase(Locale.ROOT);
        if (Arrays.stream(lower.split("/")).anyMatch(Set.of("node_modules",".venv","venv","dist","target","vendor",".git")::contains)) return false;
        return lower.matches(".*\\.(java|py|vue|ts|tsx|js|jsx|json|ya?ml|toml|md|sql|xml|properties|gradle|css|html|go|rs|kt|c|h|cs|rb|sh|ps1|txt)$")
                || lower.endsWith("dockerfile") || lower.endsWith(".gitignore");
    }
    private int priority(String entry) {
        if (entry.matches("(?is).*\t(?:README[^/]*|package.json|pyproject.toml|pom.xml)$")) return 0;
        return entry.matches("(?is).*\\.(java|py|vue|ts|tsx|go|rs|kt|js)$")?1:2;
    }
}
