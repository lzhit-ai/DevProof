package ai.devproof.git;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/** Repository registration and immutable delivery captures belong to the business service. */
@Service
public class GitInputs {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final JavaArtifacts artifacts;
    private final ControlledArtifacts reads;
    private final GitComputation compute;
    private final TransactionTemplate transactions;
    private final Set<String> credentialRefs;
    public GitInputs(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,
            BusinessAudit audit,JavaArtifacts artifacts,ControlledArtifacts reads,GitComputation compute,TransactionTemplate transactions,
            @Value("${GIT_CREDENTIAL_REFS:GITHUB_SOURCE_TOKEN}") String credentialRefs) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit;
        this.artifacts=artifacts; this.reads=reads; this.compute=compute; this.transactions=transactions;
        this.credentialRefs=new HashSet<>(Arrays.stream(credentialRefs.split(",")).map(String::strip).filter(s->!s.isEmpty()).toList());
    }
    @Transactional public List<Map<String,Object>> repositories(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("SELECT id,project_id,display_url,read_only FROM git_repositories WHERE project_id=? ORDER BY created_at DESC,id DESC",project);
    }
    @Transactional public CommandStore.Result register(UUID project,UUID actor,CommandStore.Context command,String rawUrl,String rawCredential) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaGitInputs();
        String url=UnicodeText.strip(rawUrl); validateUrl(url);
        String credential=rawCredential==null?null:UnicodeText.strip(rawCredential);
        if(credential!=null && credential.isEmpty())credential=null;
        if(credential!=null && (!credential.matches("[A-Z][A-Z0-9_]{2,159}") || !credentialRefs.contains(credential)))
            throw new ApiProblem(403,"CREDENTIAL_REF_FORBIDDEN","该仓库凭据引用未授权给业务服务");
        if(credential!=null && (!"https".equalsIgnoreCase(URI.create(url).getScheme()) || !"github.com".equalsIgnoreCase(URI.create(url).getHost())))
            throw new ApiProblem(422,"CREDENTIAL_REF_FORBIDDEN","环境凭据仅支持 GitHub HTTPS 仓库");
        String selectedCredential=credential;
        return commands.execute(command,201,()->{
            // Keep the historical URL hash and let its unique constraint serialize registration.
            int inserted=jdbc.update("INSERT INTO git_repositories(id,project_id,canonical_url_hash,display_url,credential_ref,read_only) VALUES(?,?,?,?,?,true) ON CONFLICT(project_id,canonical_url_hash) DO NOTHING",UUID.randomUUID(),project,Json.hash(url),url,selectedCredential);
            var current=jdbc.queryForMap("SELECT * FROM git_repositories WHERE project_id=? AND canonical_url_hash=? FOR UPDATE",project,Json.hash(url));
            UUID id=(UUID)current.get("id");
            if(inserted==1) {
                audit.append(project,actor,"GitRepository",id,"GIT_REPOSITORY_REGISTERED",command.correlationId(),Map.of(),null,null);
            } else if(!Objects.equals(current.get("credential_ref"),selectedCredential)) {
                jdbc.update("UPDATE git_repositories SET credential_ref=?,updated_at=clock_timestamp() WHERE id=?",selectedCredential,id);
                audit.append(project,actor,"GitRepository",id,"GIT_REPOSITORY_CREDENTIAL_REF_UPDATED",command.correlationId(),Map.of("credentialRefConfigured",selectedCredential!=null),null,null);
            }
            return jdbc.queryForMap("SELECT id,project_id,display_url,read_only FROM git_repositories WHERE id=?",id);
        });
    }
    public CommandStore.Result capture(UUID cycle,UUID repository,UUID actor,CommandStore.Context command,GitComputation.Range range) {
        // Permissions/idempotent replay are checked before network I/O, then checked again at acceptance.
        var preparation=transactions.execute(status->{
            var current=scope(cycle,repository,actor,false); owners.requireJavaGitInputs();
            var replay=commands.replay(command); if(replay==null)editable(current);
            return new Preparation(current,replay);
        });
        if(preparation.replay()!=null)return preparation.replay();
        var before=preparation.scope(); UUID project=(UUID)before.get("project_id");
        GitComputation.Frozen frozen=compute.capture(project,repository,(String)before.get("display_url"),(String)before.get("credential_ref"),range);
        return transactions.execute(status->{
            var current=scope(cycle,repository,actor,true); owners.requireJavaGitInputs();
            if(!Objects.equals(current.get("display_url"),before.get("display_url")) || !Objects.equals(current.get("credential_ref"),before.get("credential_ref"))
                || !Objects.equals(current.get("delivery_item_id"),before.get("delivery_item_id")))
                throw new ApiProblem(409,"INPUT_STALE","采集期间仓库配置或交付绑定已变化，请重新冻结");
            return commands.execute(command,201,()->{
                var diff=artifacts.save(project,"GIT_DIFF","git-diff-v2","text/x-diff",frozen.diff());
                var bundle=artifacts.save(project,"CODE_CHANGE_BUNDLE","code-change-bundle-v2","application/json",frozen.bundleJson().getBytes(StandardCharsets.UTF_8));
                UUID id=UUID.randomUUID();
                jdbc.update("""
                    INSERT INTO git_snapshots(id,cycle_id,repository_id,selected_base_ref,selected_target_ref,
                      base_sha,target_sha,merge_base_sha,effective_base_sha,capture_version,diff_mode,include_paths,exclude_paths,
                      diff_hash,coverage,diff_artifact_id,code_change_artifact_id)
                    VALUES(?,?,?,?,?,?,?,?,?,'git-capture-v4',?,CAST(? AS jsonb),CAST(? AS jsonb),?,CAST(? AS jsonb),?,?)
                    """,id,cycle,repository,range.baseRef(),range.targetRef(),frozen.base(),frozen.target(),frozen.merge(),frozen.effective(),
                    range.mode(),Json.write(range.includes()),Json.write(range.excludes()),frozen.diffHash(),Json.write(frozen.coverage()),diff.get("id"),bundle.get("id"));
                audit.append(project,actor,"GitSnapshot",id,"GIT_SNAPSHOT_FROZEN",command.correlationId(),Map.of("baseSha",frozen.base(),"targetSha",frozen.target(),
                    "diffHash",frozen.diffHash(),"diffArtifactId",diff.get("id").toString(),"codeChangeArtifactId",bundle.get("id").toString()),null,null);
                return Map.of("id",id,"base_sha",frozen.base(),"target_sha",frozen.target(),"merge_base_sha",frozen.merge(),
                    "diff_mode",range.mode(),"diff_hash",frozen.diffHash(),"coverage",frozen.coverage());
            });
        });
    }
    private record Preparation(Map<String,Object> scope,CommandStore.Result replay) {}
    private Map<String,Object> scope(UUID cycle,UUID repository,UUID actor,boolean editing) {
        var rows=jdbc.queryForList("""
            SELECT c.id,c.business_status,t.project_id,t.delivery_item_id,r.display_url,r.credential_ref,r.read_only
            FROM verification_cycles c JOIN verification_tasks t ON t.id=c.task_id
            JOIN git_repositories r ON r.id=? AND r.project_id=t.project_id
            WHERE c.id=? FOR UPDATE OF c,t FOR SHARE OF r
            """,repository,cycle);
        if(rows.isEmpty())throw new ApiProblem(422,"GIT_RANGE_INVALID","轮次或仓库不存在，或不属于同一项目");
        var row=rows.getFirst(); UUID project=(UUID)row.get("project_id"); access.require(project,actor,"SUBMITTER","ADMIN");
        if(editing)editable(row);
        if(!Boolean.TRUE.equals(row.get("read_only")))throw new ApiProblem(409,"GIT_RANGE_INVALID","仓库必须登记为只读输入");
        if(row.get("delivery_item_id")!=null) {
            var matches=jdbc.queryForList("""
                SELECT c.repository_slug FROM delivery_items i JOIN external_resources r ON r.id=i.external_resource_id
                JOIN external_connections c ON c.id=r.connection_id WHERE i.id=? AND c.project_id=?
                """,row.get("delivery_item_id"),project);
            if(matches.isEmpty() || !RepositoryIdentity.githubMatches((String)row.get("display_url"),(String)matches.getFirst().get("repository_slug")))
                throw new ApiProblem(422,"GIT_RANGE_INVALID","本次代码交付的 Git 范围必须来自 Pull Request 的同一来源仓库");
        }
        return row;
    }
    private void editable(Map<String,Object> row) {
        if(!Set.of("DRAFT","NEEDS_EVIDENCE","NEEDS_CONFIRMATION").contains(row.get("business_status")))
            throw new ApiProblem(409,"STATE_CONFLICT","当前轮次不能再冻结新的 Git 范围");
    }
    @Transactional public Map<String,Object> diff(UUID snapshot,UUID actor) {
        var rows=jdbc.queryForList("""
            SELECT s.*,s.coverage::text AS coverage_json,t.project_id FROM git_snapshots s
            JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE s.id=?
            """,snapshot);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","Git 快照不存在");
        var row=rows.getFirst(); UUID project=(UUID)row.get("project_id"); access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        if(row.get("diff_artifact_id")==null || row.get("code_change_artifact_id")==null)
            throw new ApiProblem(409,"GIT_ARTIFACT_MISSING","该历史 Git 快照未保存可回放 Diff 制品");
        var diff=artifact(project,(UUID)row.get("diff_artifact_id"),"GIT_DIFF");
        var bundleArtifact=artifact(project,(UUID)row.get("code_change_artifact_id"),"CODE_CHANGE_BUNDLE");
        if(!Objects.equals(row.get("diff_hash"),diff.get("content_hash")))throw new ApiProblem(409,"GIT_ARTIFACT_HASH_MISMATCH","冻结 Diff 摘要与制品不一致");
        reads.read((String)diff.get("storage_uri"),268435456,(String)diff.get("content_hash"));
        var bundle=Json.object(reads.text((String)bundleArtifact.get("storage_uri"),268435456,(String)bundleArtifact.get("content_hash")));
        return Map.of("snapshotId",snapshot,"baseSha",row.get("base_sha"),"targetSha",row.get("target_sha"),
            "effectiveBaseSha",row.get("effective_base_sha")==null?row.get("base_sha"):row.get("effective_base_sha"),"diffMode",row.get("diff_mode"),
            "diffHash",row.get("diff_hash"),"diffArtifactId",diff.get("id"),"coverage",Map.of("capture",Json.object((String)row.get("coverage_json")),"bundle",bundle.getOrDefault("coverage",Map.of())),
            "files",bundle.getOrDefault("files",List.of()),"contexts",bundle.getOrDefault("contexts",List.of()));
    }
    private Map<String,Object> artifact(UUID project,UUID id,String kind) {
        var rows=jdbc.queryForList("SELECT * FROM artifact_objects WHERE id=? AND project_id=? AND kind=?",id,project,kind);
        if(rows.isEmpty())throw new ApiProblem(409,"GIT_ARTIFACT_MISSING","冻结 Git 制品缺失或不属于当前项目"); return rows.getFirst();
    }
    static void validateUrl(String raw) {
        try {
            URI url=URI.create(raw);
            if((!"https".equalsIgnoreCase(url.getScheme()) && !"ssh".equalsIgnoreCase(url.getScheme())) || url.getHost()==null || url.getRawQuery()!=null || url.getRawFragment()!=null
                || url.getPath()==null || url.getPath().isEmpty() || raw.codePoints().anyMatch(c->c<32)
                || ("https".equalsIgnoreCase(url.getScheme()) && url.getUserInfo()!=null)
                || (url.getUserInfo()!=null && !url.getUserInfo().matches("[A-Za-z0-9_.-]+")))throw new IllegalArgumentException();
        } catch(IllegalArgumentException e) { throw new ApiProblem(422,"GIT_RANGE_INVALID","仓库地址必须是无内嵌密钥的 HTTPS 或 SSH 远程地址"); }
    }
}
