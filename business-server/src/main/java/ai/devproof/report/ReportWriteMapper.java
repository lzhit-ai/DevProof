package ai.devproof.report;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.*;

@Mapper
public interface ReportWriteMapper {
    @Select("SELECT r.*,c.business_status,c.sequence_no AS cycle_sequence,t.project_id,t.id AS task_id,t.requirement_key,t.delivery_item_id,a.snapshot_id,a.assessment_profile AS run_profile,a.run_status,s.assessment_profile AS snapshot_profile,s.purpose,s.snapshot_hash AS actual_snapshot_hash FROM report_versions r JOIN verification_cycles c ON c.id=r.cycle_id JOIN verification_tasks t ON t.id=c.task_id JOIN analysis_runs a ON a.id=r.run_id JOIN input_snapshots s ON s.id=a.snapshot_id WHERE r.id=#{id}")
    Map<String,Object> report(UUID id);
    @Select("SELECT a.*,s.cycle_id,s.snapshot_hash,s.purpose,s.assessment_profile AS snapshot_profile,c.business_status,c.sequence_no AS cycle_sequence,t.project_id,t.id AS task_id,t.created_by,t.requirement_key,t.delivery_item_id FROM analysis_runs a JOIN input_snapshots s ON s.id=a.snapshot_id JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE a.id=#{id}")
    Map<String,Object> run(UUID id);
    @Select("SELECT id FROM verification_cycles WHERE id=#{id} FOR UPDATE") UUID lockCycle(UUID id);
    @Select("SELECT v.*,v.evidence_ids::text AS evidence_json FROM verification_results v WHERE v.analysis_run_id=#{id} ORDER BY v.id")
    List<Map<String,Object>> results(UUID id);
    @Select("SELECT DISTINCT ON(d.result_id) d.* FROM human_verification_decisions d JOIN verification_results v ON v.id=d.result_id WHERE v.analysis_run_id=#{id} ORDER BY d.result_id,d.created_at DESC,d.id DESC")
    List<Map<String,Object>> decisions(UUID id);
    @Select("SELECT i.*,i.result_snapshot::text AS result_json,i.citation_snapshot::text AS citation_json FROM report_items i WHERE i.report_version_id=#{id} ORDER BY i.display_order")
    List<Map<String,Object>> items(UUID id);
    @Select("SELECT coalesce(max(sequence_no),0)+1 FROM report_versions WHERE cycle_id=#{id}") int nextSequence(UUID id);
    @Select("SELECT id FROM report_versions WHERE run_id=#{id} ORDER BY sequence_no LIMIT 1") UUID firstReport(UUID id);
    @Insert("INSERT INTO report_versions(id,cycle_id,sequence_no,status,parent_report_version_id,record_type,content_hash,snapshot_hash,run_id,editorial_note) VALUES(#{id},#{cycleId},#{sequence},'DRAFT',#{parentId},'DELIVERY_VERIFICATION',#{hash},#{snapshotHash},#{runId},#{note})")
    void draft(UUID id,UUID cycleId,int sequence,UUID parentId,String hash,String snapshotHash,UUID runId,String note);
    @Insert("INSERT INTO report_items(id,report_version_id,result_id,display_order,result_snapshot,citation_snapshot,disposition) VALUES(#{id},#{reportId},#{resultId},#{order},CAST(#{result} AS jsonb),CAST(#{citations} AS jsonb),#{disposition})")
    void item(UUID id,UUID reportId,UUID resultId,int order,String result,String citations,String disposition);
    @Update("UPDATE report_items SET disposition=#{disposition} WHERE id=#{id}") void disposition(UUID id,String disposition);
    @Update("UPDATE report_items SET result_snapshot=CAST(#{result} AS jsonb) WHERE id=#{id}") void itemResult(UUID id,String result);
    @Update("UPDATE report_versions SET content_hash=#{hash},editorial_note=#{note},version=version+1,updated_at=clock_timestamp() WHERE id=#{id}")
    void edit(UUID id,String hash,String note);
    @Update("UPDATE report_versions SET status=#{status},updated_at=clock_timestamp() WHERE id=#{id}") void status(UUID id,String status);
    @Update("UPDATE report_versions SET status='SUBMITTED',submitted_by=#{actorId},submitted_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=#{id}") void submit(UUID id,UUID actorId);
    @Update("UPDATE verification_cycles SET business_status=#{status},updated_at=clock_timestamp() WHERE id=#{id}") void cycleStatus(UUID id,String status);
    @Insert("INSERT INTO approval_actions(id,report_version_id,action,actor_id,reason,report_hash,snapshot_hash,run_id) VALUES(#{id},#{reportId},#{action},#{actorId},#{reason},#{reportHash},#{snapshotHash},#{runId})")
    void approval(UUID id,UUID reportId,String action,UUID actorId,String reason,String reportHash,String snapshotHash,UUID runId);
    @Select("SELECT count(*) FROM approval_actions WHERE report_version_id=#{reportId} AND action='APPROVED' AND report_hash=#{hash} AND snapshot_hash=#{snapshotHash} AND run_id=#{runId}")
    int matchingApproval(UUID reportId,String hash,String snapshotHash,UUID runId);
    @Select("SELECT id,project_id,snapshot_id,source_type,evidence_kind,locator_precision FROM evidence_items WHERE id=#{id}") Map<String,Object> evidence(UUID id);
    @Insert("INSERT INTO published_report_bodies(report_version_id,schema_version,content_hash,body_json) VALUES(#{id},#{schema},#{hash},#{body})") void body(UUID id,String schema,String hash,String body);
    @Insert("INSERT INTO published_records(id,task_id,cycle_id,report_version_id,record_type,record_no,record_hash,published_by) VALUES(#{id},#{taskId},#{cycleId},#{reportId},'DELIVERY_VERIFICATION',#{number},#{hash},#{actorId})")
    void publish(UUID id,UUID taskId,UUID cycleId,UUID reportId,String number,String hash,UUID actorId);
    @Update("UPDATE delivery_items SET verification_status=#{status},updated_at=clock_timestamp() WHERE id=#{id} AND project_id=#{projectId}")
    int deliveryStatus(UUID id,UUID projectId,String status);
    @Insert("INSERT INTO human_verification_decisions(id,result_id,decision,note,actor_id,supersedes_decision_id) VALUES(#{id},#{resultId},#{decision},#{note},#{actorId},#{previousId})")
    void decision(UUID id,UUID resultId,String decision,String note,UUID actorId,UUID previousId);
    @Select("SELECT * FROM human_verification_decisions WHERE id=#{id}") Map<String,Object> decisionById(UUID id);
    @Select("SELECT id FROM report_versions WHERE run_id=#{id} AND status='DRAFT' ORDER BY sequence_no") List<UUID> drafts(UUID id);
    @Insert("INSERT INTO audit_events(id,project_id,actor_id,aggregate_type,aggregate_id,action,correlation_id,payload) VALUES(#{id},#{projectId},#{actorId},#{type},#{aggregateId},#{action},#{correlationId},CAST(#{payload} AS jsonb))")
    void audit(UUID id,UUID projectId,UUID actorId,String type,UUID aggregateId,String action,String correlationId,String payload);
}
