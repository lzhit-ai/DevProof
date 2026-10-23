package ai.devproof.delivery;

import ai.devproof.infrastructure.*;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class DeliveryAssociationStore {
    public record Target(String kind,UUID id,String label,Map<String,Object> input,String text,UUID pullRequest,UUID gitSnapshot) {
        public Map<String,Object> manifest() { return Map.of("targetKind",kind,"targetId",id.toString(),"targetLabel",label,"inputRef",input); }
    }
    public record Change(UUID id,boolean changed) {}
    private final JdbcTemplate jdbc;
    public DeliveryAssociationStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public Map<String,Object> item(UUID project,UUID id,boolean writing) {
        var rows=jdbc.queryForList("""
            SELECT i.*,r.connection_id,r.resource_type,c.repository_slug,c.project_id AS connection_project
            FROM delivery_items i JOIN external_resources r ON r.id=i.external_resource_id
            JOIN external_connections c ON c.id=r.connection_id WHERE i.id=? AND i.project_id=?
            """+(writing?" FOR UPDATE OF i":" FOR SHARE OF i"),id,project);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","代码交付不存在");
        var item=rows.getFirst();
        if(!"PULL_REQUEST".equals(item.get("resource_type")) || !project.equals(item.get("connection_project")))throw invalid("核验事项必须来自当前项目已同步的 GitHub PR");
        return item;
    }
    public Map<String,Object> latest(UUID resource) {
        var rows=jdbc.queryForList("SELECT * FROM external_resource_revisions WHERE resource_id=? ORDER BY revision_no DESC LIMIT 1",resource);
        return rows.isEmpty()?null:rows.getFirst();
    }
    public Target target(UUID project,Map<String,Object> item,String kind,UUID id) {
        return target(project,item,kind,id,true);
    }
    public Target target(UUID project,Map<String,Object> item,String kind,UUID id,boolean requireRevision) {
        if("PULL_REQUEST".equals(kind)) {
            var rows=jdbc.queryForList("SELECT * FROM external_resources WHERE id=? AND connection_id=? AND resource_type='PULL_REQUEST'",id,item.get("connection_id"));
            if(rows.isEmpty())throw invalid("关联目标必须是同一来源仓库已同步的 PR");
            var resource=rows.getFirst(); var revision=latest(id);
            if(revision==null) {
                if(requireRevision)throw new ApiProblem(409,"STATE_CONFLICT","候选 PR 尚未同步可用版本");
                return new Target(kind,id,"PR #"+resource.get("external_key"),Map.of(),"",id,null);
            }
            String key=(String)resource.get("external_key"),title=(String)revision.get("title");
            return new Target(kind,id,"PR #"+key+" · "+title,Map.of("resourceRevisionId",revision.get("id").toString(),"contentHash",revision.get("content_hash")),
                key+" "+title+" "+revision.get("body"),id,null);
        }
        if("GIT_SNAPSHOT".equals(kind)) {
            var rows=jdbc.queryForList("""
                SELECT s.*,t.id AS task_id,t.title,t.requirement_key,r.display_url FROM git_snapshots s
                JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id
                JOIN git_repositories r ON r.id=s.repository_id AND r.project_id=t.project_id
                WHERE s.id=? AND t.project_id=? AND t.delivery_item_id=? FOR SHARE OF t,r
                """,id,project,item.get("id"));
            if(rows.isEmpty())throw invalid("Git 范围必须属于已绑定当前事项的项目核验任务");
            var snapshot=rows.getFirst();
            if(!RepositoryIdentity.githubMatches((String)snapshot.get("display_url"),(String)item.get("repository_slug")))throw invalid("研发事项只能关联同一来源仓库的 Git 范围");
            return new Target(kind,id,shortSha(snapshot.get("base_sha"))+".."+shortSha(snapshot.get("target_sha")),
                Map.of("gitSnapshotId",id.toString(),"diffHash",snapshot.get("diff_hash"),"taskId",snapshot.get("task_id").toString()),
                snapshot.get("title")+" "+snapshot.get("requirement_key")+" "+snapshot.get("selected_base_ref")+" "+snapshot.get("selected_target_ref"),null,id);
        }
        throw invalid("候选目标类型只支持已同步 PR 或已冻结 Git 范围");
    }
    public List<Map<String,Object>> targets(UUID project,Map<String,Object> item) {
        List<Map<String,Object>> result=new ArrayList<>();
        var resources=jdbc.queryForList("""
            SELECT r.id,r.external_key,v.id AS revision_id,v.title,v.content_hash FROM external_resources r
            JOIN LATERAL(SELECT id,title,content_hash FROM external_resource_revisions WHERE resource_id=r.id ORDER BY revision_no DESC LIMIT 1) v ON true
            WHERE r.connection_id=? AND r.resource_type='PULL_REQUEST' ORDER BY r.external_key DESC LIMIT 100
            """,item.get("connection_id"));
        for(var resource:resources)result.add(Map.of("target_kind","PULL_REQUEST","target_id",resource.get("id"),"target_label","PR #"+resource.get("external_key")+" · "+resource.get("title"),
            "input_ref",Map.of("resourceRevisionId",resource.get("revision_id").toString(),"contentHash",resource.get("content_hash"))));
        var snapshots=jdbc.queryForList("""
            SELECT s.* FROM git_snapshots s JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id
            WHERE t.project_id=? AND t.delivery_item_id=? ORDER BY s.created_at DESC,s.id DESC LIMIT 100
            """,project,item.get("id"));
        for(var snapshot:snapshots)result.add(Map.of("target_kind","GIT_SNAPSHOT","target_id",snapshot.get("id"),"target_label","冻结 Git 范围 · "+shortSha(snapshot.get("base_sha"))+".."+shortSha(snapshot.get("target_sha")),
            "input_ref",Map.of("gitSnapshotId",snapshot.get("id").toString(),"diffHash",snapshot.get("diff_hash"))));
        return result;
    }
    public boolean exists(UUID item,Target target) { return existing(item,target)!=null; }
    private Map<String,Object> existing(UUID item,Target target) {
        String column=target.pullRequest()!=null?"pull_request_resource_id":"git_snapshot_id";
        var rows=jdbc.queryForList("SELECT * FROM delivery_change_links WHERE delivery_item_id=? AND "+column+"=? FOR UPDATE",item,target.id());
        return rows.isEmpty()?null:rows.getFirst();
    }
    public Change upsert(UUID item,Target target,String status,String source,double confidence,String reason,UUID actor,UUID run) {
        var previous=existing(item,target); boolean confirmed="CONFIRMED".equals(status);
        if(previous==null) {
            UUID id=UUID.randomUUID();
            jdbc.update("""
                INSERT INTO delivery_change_links(id,delivery_item_id,pull_request_resource_id,git_snapshot_id,link_status,link_source,
                  confidence,reason,agent_proposal_run_id,created_by,confirmed_by,confirmed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,CASE WHEN ? THEN clock_timestamp() ELSE NULL END)
                """,id,item,target.pullRequest(),target.gitSnapshot(),status,source,confidence,reason,run,actor,confirmed?actor:null,confirmed);
            return new Change(id,true);
        }
        UUID id=(UUID)previous.get("id");
        if(confirmed && !"CONFIRMED".equals(previous.get("link_status"))) {
            jdbc.update("UPDATE delivery_change_links SET link_status='CONFIRMED',link_source=?,confidence=?,reason=?,confirmed_by=?,confirmed_at=clock_timestamp() WHERE id=?",source,confidence,reason,actor,id);
            return new Change(id,true);
        }
        return new Change(id,false);
    }
    public Map<String,Object> proposal(UUID id,UUID project,UUID item,UUID actor,Map<String,Object> manifest,int targets,int created) {
        jdbc.update("""
            INSERT INTO agent_change_proposal_runs(id,project_id,delivery_item_id,input_manifest,input_hash,rules_version,candidate_target_count,created_candidate_count,created_by)
            VALUES(?,?,?,CAST(? AS jsonb),?,?,?,?,?)
            """,id,project,item,Json.canonical(manifest),Json.hash(Json.canonical(manifest)),AssociationTokens.VERSION,targets,created,actor);
        return fields(jdbc.queryForMap("SELECT * FROM agent_change_proposal_runs WHERE id=?",id),"id","input_hash","rules_version","candidate_target_count","created_candidate_count","created_at");
    }
    public List<Map<String,Object>> links(UUID item) {
        var rows=jdbc.queryForList("""
            SELECT l.*,v.title AS pr_title,v.web_url,s.base_sha,s.target_sha FROM delivery_change_links l
            LEFT JOIN LATERAL(SELECT title,web_url FROM external_resource_revisions WHERE resource_id=l.pull_request_resource_id ORDER BY revision_no DESC LIMIT 1) v ON true
            LEFT JOIN git_snapshots s ON s.id=l.git_snapshot_id WHERE l.delivery_item_id=? ORDER BY l.created_at,l.id
            """,item);
        List<Map<String,Object>> result=new ArrayList<>();
        for(var row:rows) {
            var value=fields(row,"id","delivery_item_id","link_status","link_source","confidence","reason","agent_proposal_run_id","confirmed_at");
            boolean pr=row.get("pull_request_resource_id")!=null;
            value.put("target_kind",pr?"PULL_REQUEST":"GIT_SNAPSHOT"); value.put("target_id",row.get(pr?"pull_request_resource_id":"git_snapshot_id"));
            value.put("target_label",pr?Objects.toString(row.get("pr_title"),"已删除的 PR 来源"):row.get("base_sha")==null?"已删除的 Git 范围":shortSha(row.get("base_sha"))+".."+shortSha(row.get("target_sha")));
            value.put("target_url",pr?row.get("web_url"):null); result.add(value);
        }
        return result;
    }
    public Map<String,Object> primaryIssue(Map<String,Object> item) {
        var rows=jdbc.queryForList("""
            SELECT link.id AS source_link_id,v.id AS issue_revision_id,v.content_hash AS issue_hash,r.id AS issue_resource_id,
              r.resource_type,r.external_key,c.id AS connection_id,c.project_id,c.repository_slug,c.api_base_url,c.secret_ref,c.is_active
            FROM delivery_item_source_links link JOIN external_resource_revisions v ON v.id=link.external_resource_revision_id
            JOIN external_resources r ON r.id=v.resource_id JOIN external_connections c ON c.id=r.connection_id
            WHERE link.delivery_item_id=? AND link.link_role='PRIMARY' AND link.external_resource_revision_id IS NOT NULL
            ORDER BY link.created_at DESC,link.id DESC LIMIT 1
            """,item.get("id"));
        if(rows.isEmpty() || !"ISSUE".equals(rows.getFirst().get("resource_type")))throw new ApiProblem(409,"STATE_CONFLICT","当前事项没有可用于发现 PR 关联的 GitHub Issue 来源");
        var primary=rows.getFirst();
        if(!item.get("project_id").equals(primary.get("project_id")) || !item.get("connection_id").equals(primary.get("connection_id")))throw invalid("事项的 Issue 来源必须属于同一项目与仓库连接");
        if(!Boolean.TRUE.equals(primary.get("is_active")))throw new ApiProblem(409,"SOURCE_CONNECTION_INACTIVE","当前 GitHub 来源连接已停用");
        return primary;
    }
    public UUID pullRequest(UUID connection,String key) {
        var ids=jdbc.queryForList("SELECT id FROM external_resources WHERE connection_id=? AND resource_type='PULL_REQUEST' AND external_key=?",UUID.class,connection,key);
        return ids.isEmpty()?null:ids.getFirst();
    }
    private static String shortSha(Object value) { String text=(String)value; return text.substring(0,Math.min(12,text.length())); }
    private static Map<String,Object> fields(Map<String,Object> row,String... keys) {
        Map<String,Object> result=new LinkedHashMap<>(); for(String key:keys) { Object value=row.get(key); result.put(key,value instanceof Timestamp stamp?stamp.toInstant().toString():value); } return result;
    }
    private ApiProblem invalid(String message) { return new ApiProblem(422,"INPUT_INVALID",message); }
}
