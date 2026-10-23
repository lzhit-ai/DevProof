package ai.devproof.status;

import ai.devproof.infrastructure.*;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProjectStatusStore {
    private static final String ITEMS="""
        SELECT i.*,r.milestone_key,r.revision_no,r.content_hash AS external_content_hash,r.web_url FROM delivery_items i
        LEFT JOIN LATERAL (SELECT milestone_key,revision_no,content_hash,web_url FROM external_resource_revisions
          WHERE resource_id=i.external_resource_id ORDER BY revision_no DESC LIMIT 1) r ON true
        WHERE i.project_id=? ORDER BY i.created_at,i.id
        """;
    private static final String LINKS="""
        SELECT i.id,
          EXISTS(SELECT 1 FROM verification_tasks t JOIN published_records p ON p.task_id=t.id WHERE t.project_id=i.project_id AND t.delivery_item_id=i.id) AS formal_record,
          EXISTS(SELECT 1 FROM delivery_change_links l WHERE l.delivery_item_id=i.id AND l.link_status='CONFIRMED') AS confirmed_change,
          EXISTS(SELECT 1 FROM delivery_item_source_links l WHERE l.delivery_item_id=i.id AND l.source_revision_id IS NOT NULL) AS document_source
        FROM delivery_items i WHERE i.project_id=?
        """;
    private static final String ACTIVITY="""
        SELECT count(*) AS task_count,coalesce(sum((SELECT count(*) FROM git_snapshots g JOIN verification_cycles c ON c.id=g.cycle_id WHERE c.task_id=t.id)),0) AS git_count
        FROM verification_tasks t WHERE t.project_id=? AND t.delivery_item_id IS NULL
        """;
    private static final String RISKS="""
        SELECT r.id,r.analysis_run_id,r.severity,r.category,r.finding_kind FROM risk_findings r
        JOIN analysis_runs a ON a.id=r.analysis_run_id JOIN input_snapshots s ON s.id=a.snapshot_id
        JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id
        WHERE t.project_id=? ORDER BY r.severity,r.category,r.id
        """;
    private static final String SUCCESS="""
        SELECT r.id,r.status,r.finished_at FROM source_sync_runs r JOIN external_connections c ON c.id=r.connection_id
        WHERE c.project_id=? AND r.status IN ('SUCCEEDED','PARTIALLY_SUCCEEDED') ORDER BY r.finished_at DESC,r.id DESC LIMIT 1
        """;
    private static final String ATTEMPT="""
        SELECT r.id,r.status,r.finished_at,r.error_code FROM source_sync_runs r JOIN external_connections c ON c.id=r.connection_id
        WHERE c.project_id=? ORDER BY r.started_at DESC,r.id DESC LIMIT 1
        """;
    private static final String LAST_UPDATE="SELECT max(source_updated_at) AS updated_at FROM delivery_items WHERE project_id=?";
    private static final String HEALTH="SELECT *,scope::text AS scope_json,input_manifest::text AS manifest_json,summary::text AS summary_json,coverage::text AS coverage_json FROM project_health_snapshots WHERE project_id=? AND id=?";
    private static final String HEALTH_LIST="SELECT *,scope::text AS scope_json,input_manifest::text AS manifest_json,summary::text AS summary_json,coverage::text AS coverage_json FROM project_health_snapshots WHERE project_id=? ORDER BY as_of DESC,id DESC LIMIT 50";
    private static final String DRAFT="SELECT *,content::text AS content_json FROM project_summary_drafts WHERE project_id=? AND id=? FOR UPDATE";
    private static final String DRAFT_LIST="SELECT *,content::text AS content_json FROM project_summary_drafts WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 50";
    private static final String RECORD="SELECT * FROM project_summary_records WHERE project_id=? AND summary_draft_id=?";
    private static final String RECORD_LIST="SELECT * FROM project_summary_records WHERE project_id=? ORDER BY published_at DESC,id DESC LIMIT 50";
    private final JdbcTemplate jdbc;
    public ProjectStatusStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public List<Map<String,Object>> items(UUID project) { return jdbc.queryForList(ITEMS,project); }
    public List<Map<String,Object>> links(UUID project) { return jdbc.queryForList(LINKS,project); }
    public Map<String,Object> activity(UUID project) { return jdbc.queryForMap(ACTIVITY,project); }
    public List<Map<String,Object>> risks(UUID project) { return jdbc.queryForList(RISKS,project); }
    public Map<String,Object> successfulSync(UUID project) { return first(jdbc.queryForList(SUCCESS,project)); }
    public Map<String,Object> attemptedSync(UUID project) { return first(jdbc.queryForList(ATTEMPT,project)); }
    public Object lastUpdate(UUID project) { return jdbc.queryForMap(LAST_UPDATE,project).get("updated_at"); }
    public Instant now() { return jdbc.queryForObject("SELECT clock_timestamp()",Timestamp.class).toInstant(); }
    public Map<String,Object> health(UUID project,UUID id) { var row=first(jdbc.queryForList(HEALTH,project,id)); if(row==null)throw missing("项目态势快照不存在"); return row; }
    public List<Map<String,Object>> healthList(UUID project) { return jdbc.queryForList(HEALTH_LIST,project); }
    public Map<String,Object> draft(UUID project,UUID id) { var row=first(jdbc.queryForList(DRAFT,project,id)); if(row==null)throw missing("项目总结草稿不存在"); return row; }
    public List<Map<String,Object>> draftList(UUID project) { return jdbc.queryForList(DRAFT_LIST,project); }
    public Map<String,Object> record(UUID project,UUID draft) { return first(jdbc.queryForList(RECORD,project,draft)); }
    public List<Map<String,Object>> recordList(UUID project) { return jdbc.queryForList(RECORD_LIST,project); }
    public void createHealth(UUID id,UUID project,UUID actor,Map<String,Object> scope,Map<String,Object> input,String hash,String snapshot,Map<String,Object> summary,Map<String,Object> coverage,Instant at) {
        jdbc.update("INSERT INTO project_health_snapshots(id,project_id,scope,input_manifest,input_hash,snapshot_hash,summary,coverage,as_of,created_by) VALUES(?,?,CAST(? AS jsonb),CAST(? AS jsonb),?,?,CAST(? AS jsonb),CAST(? AS jsonb),?,?)",
            id,project,Json.canonical(scope),Json.canonical(input),hash,snapshot,Json.canonical(summary),Json.canonical(coverage),Timestamp.from(at),actor);
    }
    public void createDraft(UUID id,UUID project,UUID snapshot,String period,String title,Map<String,Object> content,String hash,UUID actor) {
        jdbc.update("INSERT INTO project_summary_drafts(id,project_id,health_snapshot_id,period_type,title,content,content_hash,draft_status,created_by) VALUES(?,?,?,?,?,CAST(? AS jsonb),?,'DRAFT',?)",id,project,snapshot,period,title,Json.canonical(content),hash,actor);
    }
    public void publish(UUID id,UUID project,UUID snapshot,UUID draft,String number,String hash,UUID actor) {
        jdbc.update("INSERT INTO project_summary_records(id,project_id,health_snapshot_id,summary_draft_id,record_no,record_hash,confirmation_type,published_by) VALUES(?,?,?,?,?,?,'PERSONAL_CONFIRMED',?)",id,project,snapshot,draft,number,hash,actor);
        jdbc.update("UPDATE project_summary_drafts SET draft_status='PUBLISHED',updated_at=clock_timestamp() WHERE id=? AND project_id=?",draft,project);
    }
    public static Map<String,Object> healthView(Map<String,Object> row) {
        var output=fields(row,"id","project_id","input_hash","snapshot_hash","as_of","created_at");
        output.put("scope",json(row,"scope_json")); output.put("input_manifest",json(row,"manifest_json")); output.put("summary",json(row,"summary_json")); output.put("coverage",json(row,"coverage_json"));return output;
    }
    public static Map<String,Object> draftView(Map<String,Object> row) {
        var output=fields(row,"id","project_id","health_snapshot_id","period_type","title","content_hash","draft_status","created_at","updated_at");output.put("content",json(row,"content_json"));return output;
    }
    public static Map<String,Object> recordView(Map<String,Object> row) { return fields(row,"id","project_id","health_snapshot_id","summary_draft_id","record_no","record_hash","confirmation_type","published_at"); }
    public static Map<String,Object> json(Map<String,Object> row,String key) { return Json.object((String)row.get(key)); }
    private static Map<String,Object> fields(Map<String,Object> row,String... keys) { var output=new LinkedHashMap<String,Object>();for(String key:keys) { Object value=row.get(key);output.put(key,value instanceof Timestamp stamp?ProjectStatus.iso(stamp):value); }return output; }
    private static Map<String,Object> first(List<Map<String,Object>> rows) { return rows.isEmpty()?null:rows.getFirst(); }
    private static ApiProblem missing(String message) { return new ApiProblem(404,"RESOURCE_NOT_FOUND",message); }
}
