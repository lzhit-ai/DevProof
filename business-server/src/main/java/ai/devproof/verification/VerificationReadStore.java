package ai.devproof.verification;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Read projections are bounded by a real run, its project and its frozen input. */
@Component
public class VerificationReadStore {
    private static final String TASK="SELECT id,project_id FROM verification_tasks WHERE id=?";
    private static final String RUN="""
        SELECT r.*,s.cycle_id,t.id AS task_id,t.project_id FROM analysis_runs r JOIN input_snapshots s ON s.id=r.snapshot_id
        JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE r.id=?
        """;
    private static final String LATEST="""
        SELECT r.id FROM analysis_runs r JOIN input_snapshots s ON s.id=r.snapshot_id JOIN verification_cycles c ON c.id=s.cycle_id
        WHERE c.task_id=? ORDER BY r.created_at DESC,r.id DESC LIMIT 1
        """;
    private static final String EVENTS="SELECT *,payload_redacted::text AS payload_json FROM run_events WHERE run_id=? ORDER BY created_at DESC,id DESC LIMIT ?";
    private static final String EVENT_CURSOR="SELECT created_at,id FROM run_events WHERE run_id=? AND id=?";
    private static final String EVENTS_BEFORE="SELECT *,payload_redacted::text AS payload_json FROM run_events WHERE run_id=? AND (created_at,id)<(?,?) ORDER BY created_at DESC,id DESC LIMIT ?";
    private static final String RESULTS="""
        SELECT r.*,r.evidence_ids::text AS evidence_json,c.claim_key,c.text AS claim_text FROM verification_results r
        JOIN claims c ON c.id=r.claim_id AND c.analysis_run_id=r.analysis_run_id WHERE r.analysis_run_id=? ORDER BY c.claim_key,r.id
        """;
    private static final String DECISIONS="""
        SELECT DISTINCT ON(d.result_id) d.* FROM human_verification_decisions d JOIN verification_results r ON r.id=d.result_id
        WHERE r.analysis_run_id=? ORDER BY d.result_id,d.created_at DESC,d.id DESC
        """;
    private static final String EVIDENCE="""
        SELECT *,locator::text AS locator_json FROM evidence_items WHERE snapshot_id=? AND project_id=?
          AND source_type<>'TOOL' AND evidence_kind<>'HTTP_QUERY' AND id=ANY(string_to_array(?,',')::uuid[]) ORDER BY captured_at,id
        """;
    private static final String ASSESSMENTS="""
        SELECT l.* FROM claim_evidence_links l JOIN claims c ON c.id=l.claim_id
        JOIN evidence_items e ON e.id=l.evidence_id AND e.snapshot_id=? AND e.project_id=?
        WHERE c.analysis_run_id=? AND l.produced_by IN ('MODEL','DETERMINISTIC','HUMAN')
          AND e.source_type<>'TOOL' AND e.evidence_kind<>'HTTP_QUERY' AND e.id=ANY(string_to_array(?,',')::uuid[]) ORDER BY l.id
        """;
    private static final String RISKS="SELECT * FROM risk_findings WHERE analysis_run_id=? ORDER BY id";
    private static final String FINDINGS="""
        SELECT f.* FROM code_review_findings f JOIN evidence_items e ON e.id=f.evidence_id AND e.snapshot_id=? AND e.project_id=?
        WHERE f.analysis_run_id=? AND e.source_type='CODE'
          AND (f.claim_id IS NULL OR EXISTS(SELECT 1 FROM claims c WHERE c.id=f.claim_id AND c.analysis_run_id=f.analysis_run_id))
        ORDER BY f.created_at,f.id
        """;
    private static final String CHALLENGES="SELECT *,evidence_ids::text AS evidence_json FROM code_review_finding_challenges WHERE analysis_run_id=? ORDER BY created_at,id";
    private static final String COVERAGE="""
        SELECT *,details::text AS details_json FROM analysis_coverages WHERE analysis_run_id=?
          AND scope_kind IN ('GIT_CAPTURE','CODE_REVIEW','FINDING_CHALLENGE','STANDARD_VERIFICATION','CONTEXT_SUPPLEMENT') ORDER BY id
        """;
    private static final String GIT_BINDING="SELECT git_snapshot_id FROM input_snapshot_git WHERE snapshot_id=?";
    private final JdbcTemplate jdbc;
    public VerificationReadStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public Map<String,Object> task(UUID id) { return first(jdbc.queryForList(TASK,id)); }
    public Map<String,Object> run(UUID id) { return first(jdbc.queryForList(RUN,id)); }
    public UUID latest(UUID task) { var ids=jdbc.queryForList(LATEST,UUID.class,task); return ids.isEmpty()?null:ids.getFirst(); }
    public List<Map<String,Object>> events(UUID run,UUID before,int limit) {
        if(before==null)return jdbc.queryForList(EVENTS,run,limit);
        var cursors=jdbc.queryForList(EVENT_CURSOR,run,before);
        if(cursors.isEmpty())throw new ai.devproof.infrastructure.ApiProblem(422,"EVENT_CURSOR_INVALID","事件游标不属于本次运行");
        var cursor=cursors.getFirst();return jdbc.queryForList(EVENTS_BEFORE,run,cursor.get("created_at"),before,limit);
    }
    public List<Map<String,Object>> results(UUID run) { return jdbc.queryForList(RESULTS,run); }
    public List<Map<String,Object>> decisions(UUID run) { return jdbc.queryForList(DECISIONS,run); }
    public List<Map<String,Object>> evidence(UUID snapshot,UUID project,Collection<UUID> refs) { return refs.isEmpty()?List.of():jdbc.queryForList(EVIDENCE,snapshot,project,csv(refs)); }
    public List<Map<String,Object>> assessments(UUID run,UUID snapshot,UUID project,Collection<UUID> refs) { return refs.isEmpty()?List.of():jdbc.queryForList(ASSESSMENTS,snapshot,project,run,csv(refs)); }
    public List<Map<String,Object>> risks(UUID run) { return jdbc.queryForList(RISKS,run); }
    public List<Map<String,Object>> findings(UUID run,UUID snapshot,UUID project) { return jdbc.queryForList(FINDINGS,snapshot,project,run); }
    public List<Map<String,Object>> challenges(UUID run) { return jdbc.queryForList(CHALLENGES,run); }
    public List<Map<String,Object>> coverage(UUID run) { return jdbc.queryForList(COVERAGE,run); }
    public UUID git(UUID snapshot) { var ids=jdbc.queryForList(GIT_BINDING,UUID.class,snapshot); return ids.isEmpty()?null:ids.getFirst(); }
    private static String csv(Collection<UUID> refs) { return String.join(",",refs.stream().map(UUID::toString).toList()); }
    private Map<String,Object> first(List<Map<String,Object>> rows) { return rows.isEmpty()?null:rows.getFirst(); }
}
