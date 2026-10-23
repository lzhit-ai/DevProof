package ai.devproof.verification;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.*;

@Mapper
public interface InputSnapshotMapper {
    @Select("SELECT c.*,t.project_id,t.delivery_item_id FROM verification_cycles c JOIN verification_tasks t ON t.id=c.task_id WHERE c.id=#{id}") Map<String,Object> cycle(UUID id);
    @Select("SELECT id FROM verification_cycles WHERE id=#{id} FOR UPDATE") UUID lockCycle(UUID id);
    @Select("SELECT * FROM input_snapshots WHERE snapshot_hash=#{hash}") Map<String,Object> byHash(String hash);
    @Select("SELECT * FROM input_snapshots WHERE id=#{id}") Map<String,Object> snapshot(UUID id);
    @Select("SELECT * FROM input_snapshot_bodies WHERE snapshot_id=#{id}") Map<String,Object> body(UUID id);
    @Select("SELECT * FROM git_snapshots WHERE id=#{id} AND cycle_id=#{cycleId} FOR SHARE") Map<String,Object> git(UUID id,UUID cycleId);
    @Select("SELECT * FROM git_repositories WHERE id=#{id} AND project_id=#{projectId}") Map<String,Object> repository(UUID projectId,UUID id);
    @Select("SELECT * FROM artifact_objects WHERE id=#{id} AND project_id=#{projectId}") Map<String,Object> artifact(UUID id,UUID projectId);
    @Select("SELECT id,claim_key,text,origin,source_manifest::text AS manifest_json FROM delivery_claim_drafts WHERE cycle_id=#{id} AND claim_status='CONFIRMED' ORDER BY claim_key FOR SHARE") List<Map<String,Object>> claims(UUID id);
    @Select("SELECT r.* FROM source_revisions r WHERE r.id=#{id} AND EXISTS(SELECT 1 FROM project_knowledge_bases k WHERE k.project_id=#{projectId} AND k.knowledge_base_id=r.knowledge_base_id) FOR SHARE OF r")
    Map<String,Object> source(UUID projectId,UUID id);
    @Select("SELECT index_version FROM project_retrieval_indexes WHERE project_id=#{id} AND status='ACTIVE' FOR SHARE") String activeIndex(UUID id);
    @Select("SELECT id,chunk_index,index_version,text_hash,content,locator::text AS locator_json FROM document_chunks WHERE source_revision_id=#{id} ORDER BY chunk_index,index_version FOR SHARE") List<Map<String,Object>> chunks(UUID id);
    @Select("SELECT r.*,er.resource_type,er.id AS external_resource_id,d.project_id AS delivery_project_id FROM delivery_item_source_links l JOIN external_resource_revisions r ON r.id=l.external_resource_revision_id JOIN delivery_items d ON d.id=l.delivery_item_id JOIN external_resources er ON er.id=d.external_resource_id WHERE l.delivery_item_id=#{id} AND l.link_role='PRIMARY' ORDER BY l.created_at DESC LIMIT 1")
    Map<String,Object> requirement(UUID id);
    @Select("SELECT e.*,e.origin_locator::text AS origin_json FROM manual_evidence e WHERE e.id=#{id} AND e.project_id=#{projectId} AND e.cycle_id=#{cycleId} FOR SHARE") Map<String,Object> manual(UUID projectId,UUID cycleId,UUID id);
    @Select("SELECT * FROM external_evidence WHERE id=#{id} AND project_id=#{projectId} AND cycle_id=#{cycleId} FOR SHARE") Map<String,Object> external(UUID projectId,UUID cycleId,UUID id);
    @Insert("INSERT INTO input_snapshots(id,cycle_id,snapshot_hash,policy_version,workflow_version,created_by,purpose,assessment_profile) VALUES(#{id},#{cycleId},#{hash},'v2','v1',#{actorId},#{purpose},'DELIVERY_VERIFICATION')")
    void create(UUID id,UUID cycleId,String hash,UUID actorId,String purpose);
    @Insert("INSERT INTO input_snapshot_bodies(snapshot_id,schema_version,content_hash,body_json) VALUES(#{id},'verification-input-v2',#{hash},#{body})") void insertBody(UUID id,String hash,String body);
    @Insert("INSERT INTO input_snapshot_sources(id,snapshot_id,source_revision_id,content_hash,parser_version) VALUES(#{id},#{snapshotId},#{sourceId},#{hash},#{parser})")
    void sourceBinding(UUID id,UUID snapshotId,UUID sourceId,String hash,String parser);
    @Insert("INSERT INTO input_snapshot_claims(id,snapshot_id,delivery_claim_draft_id,claim_key,text,origin,source_manifest,content_hash) VALUES(#{id},#{snapshotId},#{draftId},#{key},#{text},#{origin},CAST(#{manifest} AS jsonb),#{hash})")
    void claim(UUID id,UUID snapshotId,UUID draftId,String key,String text,String origin,String manifest,String hash);
    @Insert("INSERT INTO input_snapshot_git(id,snapshot_id,git_snapshot_id,diff_hash) VALUES(#{id},#{snapshotId},#{gitId},#{hash})") void gitBinding(UUID id,UUID snapshotId,UUID gitId,String hash);
    @Insert("INSERT INTO input_snapshot_external_evidence(id,snapshot_id,external_evidence_id,content_hash,commit_sha) VALUES(#{id},#{snapshotId},#{evidenceId},#{hash},#{sha})") void externalBinding(UUID id,UUID snapshotId,UUID evidenceId,String hash,String sha);
    @Insert("INSERT INTO input_snapshot_manual_evidence(id,snapshot_id,manual_evidence_id,content_hash) VALUES(#{id},#{snapshotId},#{evidenceId},#{hash})") void manualBinding(UUID id,UUID snapshotId,UUID evidenceId,String hash);
    @Insert("INSERT INTO input_snapshot_plans(snapshot_id,selection_id,plan_version_id,plan_content_hash,selection_hash) VALUES(#{id},#{selectionId},#{planId},#{planHash},#{selectionHash})")
    void plan(UUID id,UUID selectionId,UUID planId,String planHash,String selectionHash);
    @Insert("INSERT INTO evidence_items(id,project_id,snapshot_id,source_type,evidence_kind,source_revision_id,commit_sha,content_hash,excerpt_safe,locator,locator_precision,extractor_version,requires_human_confirmation) VALUES(#{id},#{projectId},#{snapshotId},#{sourceType},#{kind},#{sourceId},#{sha},#{hash},#{excerpt},CAST(#{locator} AS jsonb),'EXACT',#{extractor},#{human})")
    void evidence(UUID id,UUID projectId,UUID snapshotId,String sourceType,String kind,UUID sourceId,String sha,String hash,String excerpt,String locator,String extractor,boolean human);
    @Insert("INSERT INTO audit_events(id,project_id,actor_id,aggregate_type,aggregate_id,action,correlation_id,payload) VALUES(#{id},#{projectId},#{actorId},'InputSnapshot',#{snapshotId},#{action},#{correlationId},CAST(#{payload} AS jsonb))")
    void audit(UUID id,UUID projectId,UUID actorId,UUID snapshotId,String action,String correlationId,String payload);
}
