package ai.devproof.securitybaseline;

import ai.devproof.infrastructure.*;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class SecurityStore {
    private static final String REPOSITORY="SELECT id FROM git_repositories WHERE project_id=? AND id=? FOR SHARE";
    private static final String ARTIFACT="SELECT a.*,a.coverage::text AS coverage_json,(SELECT count(*) FROM security_findings f WHERE f.scan_artifact_id=a.id) AS finding_count FROM security_scan_artifacts a WHERE a.project_id=? AND a.id=?";
    private static final String ARTIFACTS="SELECT a.*,a.coverage::text AS coverage_json,(SELECT count(*) FROM security_findings f WHERE f.scan_artifact_id=a.id) AS finding_count FROM security_scan_artifacts a WHERE a.project_id=? ORDER BY a.created_at DESC,a.id DESC LIMIT 100";
    private static final String TREND_ARTIFACTS="SELECT a.*,a.coverage::text AS coverage_json FROM security_scan_artifacts a WHERE a.project_id=? ORDER BY a.created_at,a.id LIMIT 300";
    private static final String FINDINGS="""
        SELECT f.*,f.locator::text AS locator_json FROM security_findings f JOIN security_scan_artifacts a ON a.id=f.scan_artifact_id
        WHERE a.project_id=? AND a.id=ANY(string_to_array(?,',')::uuid[]) ORDER BY f.scan_artifact_id,f.fingerprint,f.id
        """;
    private static final String FINDING="SELECT f.*,f.locator::text AS locator_json FROM security_findings f JOIN security_scan_artifacts a ON a.id=f.scan_artifact_id WHERE a.project_id=? AND f.id=? FOR UPDATE OF f";
    private static final String BASELINE="SELECT *,input_manifest::text AS manifest_json,summary::text AS summary_json,coverage::text AS coverage_json FROM security_baseline_snapshots WHERE project_id=? AND id=? FOR UPDATE";
    private static final String BASELINES="SELECT *,input_manifest::text AS manifest_json,summary::text AS summary_json,coverage::text AS coverage_json FROM security_baseline_snapshots WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 50";
    private static final String RECORD="SELECT * FROM security_baseline_records WHERE project_id=? AND baseline_snapshot_id=?";
    private static final String RECORDS="SELECT * FROM security_baseline_records WHERE project_id=? ORDER BY confirmed_at DESC,id DESC LIMIT 50";
    private final JdbcTemplate jdbc;
    public SecurityStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public void repository(UUID project,UUID id) { if(jdbc.queryForList(REPOSITORY,project,id).isEmpty())throw missing("Git 仓库不存在或不属于当前项目"); }
    public Map<String,Object> artifact(UUID project,UUID id) { return required(jdbc.queryForList(ARTIFACT,project,id),"安全扫描输入不存在"); }
    public List<Map<String,Object>> artifacts(UUID project) { return jdbc.queryForList(ARTIFACTS,project); }
    public List<Map<String,Object>> trendArtifacts(UUID project) { return jdbc.queryForList(TREND_ARTIFACTS,project); }
    public List<Map<String,Object>> findings(UUID project,Collection<UUID> artifacts) { return artifacts.isEmpty()?List.of():jdbc.queryForList(FINDINGS,project,artifacts.stream().map(UUID::toString).collect(Collectors.joining(","))); }
    public Map<String,Object> finding(UUID project,UUID id) { return required(jdbc.queryForList(FINDING,project,id),"安全风险不存在"); }
    public Map<String,Object> baseline(UUID project,UUID id) { return required(jdbc.queryForList(BASELINE,project,id),"安全基线不存在"); }
    public List<Map<String,Object>> baselines(UUID project) { return jdbc.queryForList(BASELINES,project); }
    public Map<String,Object> record(UUID project,UUID baseline) { var rows=jdbc.queryForList(RECORD,project,baseline);return rows.isEmpty()?null:rows.getFirst(); }
    public List<Map<String,Object>> records(UUID project) { return jdbc.queryForList(RECORDS,project); }
    public Instant now() { return jdbc.queryForObject("SELECT clock_timestamp()",Timestamp.class).toInstant(); }
    public void createArtifact(UUID id,UUID project,UUID repository,String sha,String type,String scanner,String version,String rules,Map<String,Object> coverage,String hash,String uri,UUID actor) {
        jdbc.update("INSERT INTO security_scan_artifacts(id,project_id,repository_id,target_sha,scan_type,scanner_name,scanner_version,rule_set_version,coverage,content_hash,artifact_uri,imported_by) VALUES(?,?,?,?,?,?,?,?,CAST(? AS jsonb),?,?,?)",id,project,repository,sha,type,scanner,version,rules,Json.canonical(coverage),hash,uri,actor);
    }
    public void createFinding(UUID id,UUID artifact,String fingerprint,String severity,String category,String title,Map<String,Object> locator) {
        jdbc.update("INSERT INTO security_findings(id,scan_artifact_id,fingerprint,severity,category,title,locator,finding_status,status_reason) VALUES(?,?,?,?,?,?,CAST(? AS jsonb),'OPEN','')",id,artifact,fingerprint,severity,category,title,Json.canonical(locator));
    }
    public void status(UUID id,String status,String reason,UUID actor) { jdbc.update("UPDATE security_findings SET finding_status=?,status_reason=?,status_updated_by=?,status_updated_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=?",status,reason,actor,id); }
    public void createBaseline(UUID id,UUID project,UUID repository,String sha,Map<String,Object> manifest,String hash,String snapshotHash,Map<String,Object> summary,Map<String,Object> coverage,UUID actor,Instant at) {
        jdbc.update("INSERT INTO security_baseline_snapshots(id,project_id,repository_id,target_sha,input_manifest,input_hash,snapshot_hash,summary,coverage,created_by,created_at) VALUES(?,?,?,?,CAST(? AS jsonb),?,?,CAST(? AS jsonb),CAST(? AS jsonb),?,?)",id,project,repository,sha,Json.canonical(manifest),hash,snapshotHash,Json.canonical(summary),Json.canonical(coverage),actor,Timestamp.from(at));
    }
    public void confirm(UUID id,UUID project,UUID baseline,String number,String hash,String reason,UUID actor) {
        jdbc.update("INSERT INTO security_baseline_records(id,project_id,baseline_snapshot_id,record_no,record_hash,confirmation_reason,confirmed_by) VALUES(?,?,?,?,?,?,?)",id,project,baseline,number,hash,reason,actor);
    }
    public static Map<String,Object> artifactView(Map<String,Object> row) { var view=fields(row,"id","project_id","repository_id","target_sha","scan_type","scanner_name","scanner_version","rule_set_version","content_hash","finding_count","created_at");view.put("coverage",json(row,"coverage_json"));return view; }
    public static Map<String,Object> findingView(Map<String,Object> row) { var view=fields(row,"id","scan_artifact_id","fingerprint","severity","category","title","finding_status","status_reason","status_updated_at");view.put("locator",json(row,"locator_json"));return view; }
    public static Map<String,Object> baselineView(Map<String,Object> row) { var view=fields(row,"id","project_id","repository_id","target_sha","input_hash","snapshot_hash","created_at");view.put("input_manifest",json(row,"manifest_json"));view.put("summary",json(row,"summary_json"));view.put("coverage",json(row,"coverage_json"));return view; }
    public static Map<String,Object> recordView(Map<String,Object> row) { return fields(row,"id","project_id","baseline_snapshot_id","record_no","record_hash","confirmation_reason","confirmed_at"); }
    static Map<String,Object> fields(Map<String,Object> row,String... keys) { var view=new LinkedHashMap<String,Object>();for(String key:keys) { Object value=row.get(key);view.put(key,value instanceof Timestamp?UtcTime.iso(value):value); }return view; }
    static Map<String,Object> json(Map<String,Object> row,String key) { return Json.object((String)row.get(key)); }
    private static Map<String,Object> required(List<Map<String,Object>> rows,String message) { if(rows.isEmpty())throw missing(message);return rows.getFirst(); }
    private static ApiProblem missing(String message) { return new ApiProblem(404,"RESOURCE_NOT_FOUND",message); }
}
