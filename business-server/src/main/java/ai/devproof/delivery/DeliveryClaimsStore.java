package ai.devproof.delivery;

import ai.devproof.infrastructure.*;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class DeliveryClaimsStore {
    private final JdbcTemplate jdbc;
    public DeliveryClaimsStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public Map<String,Object> scope(UUID project,UUID task) {
        var rows=jdbc.queryForList("""
            SELECT t.id AS task_id,t.project_id,t.delivery_item_id,c.id AS cycle_id,c.business_status
            FROM verification_cycles c JOIN verification_tasks t ON t.id=c.task_id
            WHERE t.id=? AND t.project_id=? AND c.id=(SELECT id FROM verification_cycles WHERE task_id=t.id ORDER BY sequence_no DESC LIMIT 1)
            FOR UPDATE OF c,t
            """,task,project);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","核验任务或轮次不存在"); return rows.getFirst();
    }
    public void editable(Map<String,Object> scope,boolean proposing) {
        if(!Set.of("DRAFT","NEEDS_EVIDENCE","NEEDS_CONFIRMATION").contains(scope.get("business_status"))
            || jdbc.queryForObject("SELECT count(*) FROM input_snapshots WHERE cycle_id=? AND purpose='FORMAL'",Integer.class,scope.get("cycle_id"))>0)
            throw new ApiProblem(409,"STATE_CONFLICT","本轮已冻结或开始核验；调整交付主张需要新的轮次");
        if(proposing && jdbc.queryForObject("SELECT count(*) FROM delivery_claim_drafts WHERE cycle_id=? AND claim_status='CONFIRMED'",Integer.class,scope.get("cycle_id"))>0)
            throw new ApiProblem(409,"STATE_CONFLICT","本轮已有人工确认的主张，不能用模型候选覆盖");
    }
    public Map<String,Object> pullRequest(Map<String,Object> scope) {
        var rows=jdbc.queryForList("""
            SELECT i.id AS item_id,r.id AS resource_id,v.id AS revision_id,v.content_hash,v.title,v.body,v.web_url
            FROM delivery_items i JOIN external_resources r ON r.id=i.external_resource_id AND r.resource_type='PULL_REQUEST'
            JOIN external_connections c ON c.id=r.connection_id AND c.project_id=i.project_id
            JOIN LATERAL(SELECT * FROM external_resource_revisions WHERE resource_id=r.id ORDER BY revision_no DESC LIMIT 1) v ON true
            WHERE i.id=? AND i.project_id=?
            """,scope.get("delivery_item_id"),scope.get("project_id"));
        if(rows.isEmpty())throw new ApiProblem(422,"INPUT_INVALID","当前任务缺少可用于提取主张的同步 Pull Request 版本"); return rows.getFirst();
    }
    public Map<String,Object> source(UUID project,UUID id) {
        var rows=jdbc.queryForList("""
            SELECT s.* FROM source_revisions s WHERE s.id=? AND s.processing_status='READY'
              AND EXISTS(SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=? AND b.knowledge_base_id=s.knowledge_base_id)
            FOR SHARE OF s
            """,id,project);
        if(rows.isEmpty())throw new ApiProblem(409,"SOURCE_NOT_READY","所选资料不再属于当前项目可用的已就绪资料范围"); return rows.getFirst();
    }
    public List<Map<String,Object>> drafts(UUID cycle,boolean includeDiscarded) {
        return jdbc.queryForList("SELECT *,source_manifest::text AS manifest_json FROM delivery_claim_drafts WHERE cycle_id=?"+(includeDiscarded?"":" AND claim_status<>'DISCARDED'")+" ORDER BY created_at,claim_key",cycle);
    }
    public List<Map<String,Object>> views(UUID cycle) { return drafts(cycle,false).stream().map(DeliveryClaimsStore::view).toList(); }
    public static Map<String,Object> view(Map<String,Object> row) {
        Map<String,Object> value=new LinkedHashMap<>();
        for(String key:List.of("id","claim_key","text","rationale","origin","created_at","updated_at")) { Object raw=row.get(key); value.put(key,raw instanceof Timestamp stamp?stamp.toInstant().toString():raw); }
        value.put("status",row.get("claim_status")); value.put("source_manifest",Json.object((String)row.get("manifest_json"))); return value;
    }
    public void discard(UUID cycle,String status) { jdbc.update("UPDATE delivery_claim_drafts SET claim_status='DISCARDED',updated_at=clock_timestamp() WHERE cycle_id=? AND claim_status=?",cycle,status); }
    public void confirm(UUID id,UUID cycle,String key,String text,UUID actor,boolean existing) {
        if(existing)jdbc.update("UPDATE delivery_claim_drafts SET text=?,claim_status='CONFIRMED',confirmed_by=?,confirmed_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=? AND cycle_id=?",text,actor,id,cycle);
        else jdbc.update("""
            INSERT INTO delivery_claim_drafts(id,cycle_id,claim_key,text,rationale,origin,claim_status,source_manifest,created_by,confirmed_by,confirmed_at)
            VALUES(?,?,?,?,'提交人补充的交付主张','HUMAN','CONFIRMED','{"source":"USER_CONFIRMED"}',?,?,clock_timestamp())
            """,id,cycle,key,text,actor,actor);
    }
    public void candidate(UUID cycle,String key,String text,String rationale,Map<String,Object> manifest,UUID actor) {
        jdbc.update("""
            INSERT INTO delivery_claim_drafts(id,cycle_id,claim_key,text,rationale,origin,claim_status,source_manifest,created_by)
            VALUES(?,?,?,?,?,'MODEL','CANDIDATE',CAST(? AS jsonb),?)
            ON CONFLICT(cycle_id,claim_key) DO UPDATE SET text=excluded.text,rationale=excluded.rationale,claim_status='CANDIDATE',
              source_manifest=excluded.source_manifest,updated_at=clock_timestamp()
            """,UUID.randomUUID(),cycle,key,text,rationale,Json.canonical(manifest),actor);
    }
    public boolean active(UUID cycle) { return jdbc.queryForObject("SELECT count(*) FROM delivery_claim_proposal_runs WHERE cycle_id=? AND status IN ('QUEUED','RUNNING')",Integer.class,cycle)>0; }
    public void create(UUID id,UUID project,UUID task,UUID cycle,UUID actor,String input,Map<String,Object> manifest) {
        jdbc.update("INSERT INTO delivery_claim_proposal_runs(id,project_id,task_id,cycle_id,input_json,input_hash,source_manifest,status,created_by) VALUES(?,?,?,?,?,?,CAST(? AS jsonb),'QUEUED',?)",id,project,task,cycle,input,Json.hash(input),Json.canonical(manifest),actor);
    }
    public Map<String,Object> run(UUID id) {
        var rows=jdbc.queryForList("SELECT *,source_manifest::text AS manifest_json FROM delivery_claim_proposal_runs WHERE id=? FOR UPDATE",id);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","主张提取运行不存在"); return rows.getFirst();
    }
    public void status(UUID id,String status,String code) {
        jdbc.update("UPDATE delivery_claim_proposal_runs SET status=?,last_error_code=?,finished_at=CASE WHEN ? IN ('QUEUED','RUNNING') THEN NULL ELSE clock_timestamp() END WHERE id=?",status,code,status,id);
    }
    public List<Map<String,Object>> runs(UUID cycle) {
        var rows=jdbc.queryForList("""
            SELECT r.id,r.status,r.input_hash,r.created_at,r.finished_at,r.last_error_code,t.id AS agent_task_id
            FROM delivery_claim_proposal_runs r JOIN agent_tasks t ON t.claim_proposal_run_id=r.id
            WHERE r.cycle_id=? ORDER BY r.created_at DESC,r.id DESC LIMIT 20
            """,cycle);
        return rows.stream().map(row->{ Map<String,Object> view=new LinkedHashMap<>(row); for(String key:List.of("created_at","finished_at"))if(view.get(key) instanceof Timestamp stamp)view.put(key,stamp.toInstant().toString()); view.put("poll_url","/api/v1/agent-tasks/"+row.get("agent_task_id")); return view; }).toList();
    }
}
