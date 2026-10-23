package ai.devproof.planning;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.*;

@Mapper
public interface PlanBindingMapper {
    @Select("SELECT c.*,t.project_id,t.title AS task_title FROM verification_cycles c JOIN verification_tasks t ON t.id=c.task_id WHERE c.id=#{cycleId} AND t.project_id=#{projectId} FOR UPDATE OF c")
    Map<String,Object> lockCycle(UUID projectId,UUID cycleId);
    @Select("SELECT c.*,t.project_id,t.title AS task_title FROM verification_cycles c JOIN verification_tasks t ON t.id=c.task_id WHERE c.id=#{cycleId} AND t.project_id=#{projectId}")
    Map<String,Object> cycle(UUID projectId,UUID cycleId);
    @Select("SELECT EXISTS(SELECT 1 FROM input_snapshots WHERE cycle_id=#{cycleId} AND purpose='FORMAL')")
    boolean frozen(UUID cycleId);
    @Select("SELECT v.id,v.sequence_no,v.status,v.content_hash,v.confirmed_at,r.idea_id,r.revision_no AS idea_revision_no,i.title,rs.repository_id,rs.target_sha FROM plan_versions v JOIN idea_revisions r ON r.id=v.idea_revision_id JOIN ideas i ON i.id=r.idea_id JOIN planning_runs pr ON pr.id=v.planning_run_id JOIN planning_input_snapshots ps ON ps.id=pr.snapshot_id JOIN repository_snapshots rs ON rs.id=ps.repository_snapshot_id WHERE i.project_id=#{projectId} AND v.status IN ('CONFIRMED','SUPERSEDED') AND v.confirmed_at IS NOT NULL ORDER BY v.confirmed_at DESC,v.id LIMIT 100")
    List<Map<String,Object>> options(UUID projectId);
    @Select("SELECT p.* FROM cycle_plan_selection_current c JOIN cycle_plan_selections p ON p.id=c.selection_id WHERE c.cycle_id=#{cycleId}")
    Map<String,Object> current(UUID cycleId);
    @Select("SELECT * FROM delivery_claim_drafts WHERE id=#{claimId} AND cycle_id=#{cycleId} FOR SHARE")
    Map<String,Object> claim(UUID cycleId,UUID claimId);
    @Select("SELECT coalesce(max(sequence_no),0)+1 FROM cycle_plan_selections WHERE cycle_id=#{cycleId}")
    int nextSequence(UUID cycleId);
    @Insert("INSERT INTO cycle_plan_selections(id,cycle_id,plan_version_id,sequence_no,plan_content_hash,content_hash,body_json,created_by) VALUES(#{id},#{cycleId},#{planId},#{sequence},#{planHash},#{hash},#{body},#{actorId})")
    void selection(UUID id,UUID cycleId,UUID planId,int sequence,String planHash,String hash,String body,UUID actorId);
    @Insert("INSERT INTO cycle_plan_selection_current(cycle_id,selection_id) VALUES(#{cycleId},#{selectionId}) ON CONFLICT(cycle_id) DO UPDATE SET selection_id=excluded.selection_id")
    void select(UUID cycleId,UUID selectionId);
    @Delete("DELETE FROM cycle_plan_selection_current WHERE cycle_id=#{cycleId}")
    void clear(UUID cycleId);
    @Select("SELECT p.id,p.sequence_no,p.content_hash,p.body_json,p.created_at FROM cycle_plan_selections p WHERE p.cycle_id=#{cycleId} ORDER BY p.sequence_no DESC")
    List<Map<String,Object>> history(UUID cycleId);
    @Select("SELECT s.id AS snapshot_id,s.snapshot_hash,b.selection_id,b.selection_hash,b.plan_version_id,b.plan_content_hash,r.id AS run_id,r.run_status,g.target_sha,g.diff_hash FROM input_snapshots s JOIN input_snapshot_plans b ON b.snapshot_id=s.id LEFT JOIN analysis_runs r ON r.snapshot_id=s.id LEFT JOIN input_snapshot_git ig ON ig.snapshot_id=s.id LEFT JOIN git_snapshots g ON g.id=ig.git_snapshot_id WHERE s.cycle_id=#{cycleId} ORDER BY s.created_at,r.created_at")
    List<Map<String,Object>> runs(UUID cycleId);
    @Select("SELECT c.claim_key,c.id AS claim_id,v.id AS result_id,v.status,v.reason,v.evidence_ids::text AS evidence_ids_json FROM claims c LEFT JOIN verification_results v ON v.claim_id=c.id AND v.analysis_run_id=c.analysis_run_id WHERE c.analysis_run_id=#{runId} ORDER BY c.claim_key")
    List<Map<String,Object>> results(UUID runId);
    @Select("SELECT r.id,r.sequence_no,r.status,r.content_hash,r.snapshot_hash,p.id AS published_record_id,p.record_no,p.record_hash FROM report_versions r LEFT JOIN published_records p ON p.report_version_id=r.id WHERE r.run_id=#{runId} ORDER BY r.sequence_no")
    List<Map<String,Object>> reports(UUID runId);
}
