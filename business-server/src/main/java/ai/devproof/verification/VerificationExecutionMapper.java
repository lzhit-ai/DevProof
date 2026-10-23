package ai.devproof.verification;

import java.util.*;
import org.apache.ibatis.annotations.*;

@Mapper
public interface VerificationExecutionMapper {
    @Select("SELECT s.*,c.business_status,t.id AS task_id,t.project_id,t.created_by FROM input_snapshots s JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE s.id=#{id}") Map<String,Object> snapshotScope(UUID id);
    @Select("SELECT a.*,s.cycle_id,s.snapshot_hash,t.id AS task_id,t.project_id FROM analysis_runs a JOIN input_snapshots s ON s.id=a.snapshot_id JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE a.id=#{id}") Map<String,Object> run(UUID id);
    @Select("SELECT id FROM analysis_runs WHERE snapshot_id=#{snapshot} AND analysis_config_hash=#{hash} AND run_status IN ('QUEUED','RUNNING')") UUID active(UUID snapshot,String hash);
    @Insert("INSERT INTO analysis_runs(id,snapshot_id,assessment_profile,analysis_config_hash,run_status,manifest_hash,checkpoint_ns,executor_owner,plan_version_id,plan_baseline_hash) VALUES(#{id},#{snapshot},'DELIVERY_VERIFICATION',#{hash},'QUEUED',#{manifest},#{namespace},'JAVA',#{plan},#{baseline})")
    void createRun(UUID id,UUID snapshot,String hash,String manifest,String namespace,UUID plan,String baseline);
    @Insert("INSERT INTO analysis_run_manifests(id,run_id,workflow_version,rule_set_version,prompt_set_version,generation_model,embedding_model,schema_version,degradation) VALUES(#{id},#{run},'delivery-agent-v3','delivery-verdict-v2','verification-agents-v1',#{model},#{embedding},'verification-result-v1','{}')")
    void manifest(UUID id,UUID run,String model,String embedding);
    @Select("SELECT * FROM input_snapshot_plans WHERE snapshot_id=#{id}") Map<String,Object> plan(UUID id);
    @Select("SELECT id,claim_key,text,source_manifest::text AS manifest_json FROM input_snapshot_claims WHERE snapshot_id=#{id} ORDER BY claim_key") List<Map<String,Object>> frozenClaims(UUID id);
    @Insert("INSERT INTO claims(id,analysis_run_id,claim_key,claim_type,text,authority_level) VALUES(#{id},#{run},#{key},'USER_CONFIRMED_DELIVERY',#{text},3)") void claim(UUID id,UUID run,String key,String text);
    @Select("SELECT c.*,s.source_manifest::text AS manifest_json FROM claims c JOIN analysis_runs r ON r.id=c.analysis_run_id LEFT JOIN input_snapshot_claims s ON s.snapshot_id=r.snapshot_id AND s.claim_key=c.claim_key WHERE c.analysis_run_id=#{run} ORDER BY c.claim_key") List<Map<String,Object>> claims(UUID run);
    @Select("SELECT e.*,e.locator::text AS locator_json FROM evidence_items e WHERE e.snapshot_id=#{snapshot} ORDER BY e.source_type,e.captured_at,e.id") List<Map<String,Object>> evidence(UUID snapshot);
    @Select("SELECT g.*,g.coverage::text AS coverage_json FROM input_snapshot_git b JOIN git_snapshots g ON g.id=b.git_snapshot_id WHERE b.snapshot_id=#{id}") Map<String,Object> git(UUID id);
    @Select("SELECT * FROM artifact_objects WHERE id=#{id} AND project_id=#{project}") Map<String,Object> artifact(UUID id,UUID project);
    @Select("SELECT e.id FROM evidence_items e WHERE e.snapshot_id=#{snapshot} AND e.source_type='CODE' AND e.evidence_kind='GIT_DIFF_HUNK' AND e.commit_sha=#{sha} AND e.locator->>'artifactId'=#{artifact} AND e.locator->>'path'=#{path} AND e.locator->>'hunk'=#{header} ORDER BY e.captured_at,e.id LIMIT 1")
    UUID hunkEvidence(UUID snapshot,String sha,String artifact,String path,String header);
    @Insert("INSERT INTO analysis_coverages(id,analysis_run_id,scope_kind,scope_ref,state,reason_code,details) VALUES(#{id},#{run},#{kind},#{reference},#{state},#{reason},CAST(#{details} AS jsonb))")
    void insertCoverage(UUID id,UUID run,String kind,String reference,String state,String reason,String details);
    @Select("SELECT scope_kind,scope_ref,state,reason_code,details::text AS details_json FROM analysis_coverages WHERE analysis_run_id=#{id} ORDER BY scope_kind,id") List<Map<String,Object>> coverage(UUID id);
    @Select("SELECT * FROM analysis_run_orchestration_snapshots WHERE run_id=#{id}") Map<String,Object> orchestration(UUID id);
    @Select("SELECT template_snapshot::text AS template_json,nodes_snapshot::text AS nodes_json,content_hash,id,raw_body FROM analysis_run_orchestration_snapshots WHERE run_id=#{id}") Map<String,Object> orchestrationJson(UUID id);
    @Update("UPDATE verification_cycles SET business_status=#{status},active_run_id=#{run},updated_at=clock_timestamp() WHERE id=#{id}") void cycle(UUID id,UUID run,String status);
    @Update("UPDATE analysis_runs SET run_status=#{status},started_at=CASE WHEN #{status}='RUNNING' THEN coalesce(started_at,clock_timestamp()) ELSE started_at END,finished_at=CASE WHEN #{status} IN ('SUCCEEDED','PARTIALLY_COMPLETED','FAILED','CANCELLED') THEN clock_timestamp() ELSE NULL END,updated_at=clock_timestamp() WHERE id=#{id}") void status(UUID id,String status);
    @Update("UPDATE analysis_runs SET cancel_requested_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=#{id}") void cancelled(UUID id);
    @Select("SELECT id FROM agent_tasks WHERE analysis_run_id=#{id}") UUID agentTask(UUID id);
    @Insert("INSERT INTO run_events(id,run_id,node_id,event_type,status,correlation_id,payload_redacted) VALUES(#{id},#{run},#{node},#{type},#{status},#{correlation},CAST(#{payload} AS jsonb))")
    void event(UUID id,UUID run,String node,String type,String status,String correlation,String payload);
    @Insert("INSERT INTO claim_evidence_links(id,claim_id,evidence_id,relation,reason,confidence,produced_by,requires_human_confirmation) VALUES(#{id},#{claim},#{evidence},#{relation},#{reason},#{confidence},#{producer},#{human})")
    void link(UUID id,UUID claim,UUID evidence,String relation,String reason,double confidence,String producer,boolean human);
    @Insert("INSERT INTO verification_results(id,analysis_run_id,claim_id,protocol_version,status,reason,evidence_ids,requires_human_confirmation,produced_by) VALUES(#{id},#{run},#{claim},'v1',#{status},#{reason},CAST(#{evidence} AS jsonb),#{human},'DETERMINISTIC')")
    void result(UUID id,UUID run,UUID claim,String status,String reason,String evidence,boolean human);
    @Insert("INSERT INTO risk_findings(id,analysis_run_id,claim_id,evidence_id,severity,category,finding_kind,recommendation) VALUES(#{id},#{run},#{claim},#{evidence},#{severity},'EVIDENCE_CONFLICT','DETERMINISTIC',#{recommendation})")
    void risk(UUID id,UUID run,UUID claim,UUID evidence,String severity,String recommendation);
    @Insert("INSERT INTO code_review_findings(id,analysis_run_id,evidence_id,claim_id,fingerprint,severity,finding_kind,title,problem,trigger_scenario,recommendation,confidence,produced_by,requires_human_confirmation,schema_version) VALUES(#{id},#{run},#{evidence},#{claim},#{hash},#{severity},#{kind},#{title},#{problem},#{trigger},#{recommendation},#{confidence},'MODEL',true,'code-review-finding-v2')")
    void finding(UUID id,UUID run,UUID evidence,UUID claim,String hash,String severity,String kind,String title,String problem,String trigger,String recommendation,double confidence);
    @Insert("INSERT INTO code_review_finding_challenges(id,analysis_run_id,finding_id,fingerprint,verdict,reason,evidence_ids,model_call_id,schema_version) VALUES(#{id},#{run},#{finding},#{hash},#{verdict},#{reason},CAST(#{evidence} AS jsonb),#{modelCall},'code-review-challenge-v2')")
    void challenge(UUID id,UUID run,UUID finding,String hash,String verdict,String reason,String evidence,UUID modelCall);
    @Select("SELECT id FROM model_calls WHERE agent_task_attempt_id=#{attempt} AND operation='CODE_REVIEW_CHALLENGE' AND status='SUCCEEDED' ORDER BY created_at DESC,id DESC LIMIT 1") UUID challengeCall(UUID attempt);
    @Update("UPDATE analysis_run_manifests SET degradation=CAST(#{value} AS jsonb) WHERE run_id=#{id}") void degradation(UUID id,String value);
    @Insert("INSERT INTO audit_events(id,project_id,actor_id,aggregate_type,aggregate_id,action,correlation_id,payload) VALUES(#{id},#{project},#{actor},'AnalysisRun',#{run},#{action},#{correlation},CAST(#{payload} AS jsonb))")
    void audit(UUID id,UUID project,UUID actor,UUID run,String action,String correlation,String payload);
}
