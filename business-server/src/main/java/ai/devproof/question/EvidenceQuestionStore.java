package ai.devproof.question;

import ai.devproof.infrastructure.*;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class EvidenceQuestionStore {
    private final JdbcTemplate jdbc;
    public EvidenceQuestionStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public Map<String,Object> snapshot(UUID id) {
        var rows=jdbc.queryForList("SELECT s.id,s.snapshot_hash,t.project_id FROM input_snapshots s JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE s.id=?",id);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","输入快照不存在"); return rows.getFirst();
    }
    public void create(UUID id,UUID project,UUID snapshot,UUID actor,String input) {
        jdbc.update("INSERT INTO evidence_question_runs(id,project_id,snapshot_id,created_by,input_json,input_hash,status) VALUES(?,?,?,?,?,?,'QUEUED')",id,project,snapshot,actor,input,Json.hash(input));
    }
    public Map<String,Object> lock(UUID id) {
        var rows=jdbc.queryForList("SELECT * FROM evidence_question_runs WHERE id=? FOR UPDATE",id);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","问答运行不存在"); return rows.getFirst();
    }
    public void status(UUID id,String status,String code) {
        jdbc.update("UPDATE evidence_question_runs SET status=?,last_error_code=?,finished_at=CASE WHEN ? IN ('QUEUED','RUNNING') THEN NULL ELSE clock_timestamp() END WHERE id=?",status,code,status,id);
    }
    public void accepted(UUID id,Map<String,Object> result) {
        jdbc.update("UPDATE evidence_question_runs SET status='SUCCEEDED',result_json=?,last_error_code=NULL,finished_at=clock_timestamp() WHERE id=?",Json.canonical(result),id);
    }
    public List<Map<String,Object>> list(UUID snapshot,UUID project,UUID actor,boolean admin) {
        return jdbc.queryForList("SELECT q.*,t.id AS agent_task_id FROM evidence_question_runs q JOIN agent_tasks t ON t.question_run_id=q.id WHERE q.snapshot_id=? AND q.project_id=? AND (? OR q.created_by=?) ORDER BY q.created_at DESC,q.id DESC LIMIT 20",snapshot,project,admin,actor).stream().map(EvidenceQuestionStore::view).toList();
    }
    public Map<String,Object> get(UUID snapshot,UUID id,UUID project) {
        var rows=jdbc.queryForList("SELECT q.*,t.id AS agent_task_id FROM evidence_question_runs q JOIN agent_tasks t ON t.question_run_id=q.id WHERE q.snapshot_id=? AND q.id=? AND q.project_id=?",snapshot,id,project);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","问答运行不存在"); return rows.getFirst();
    }
    public static Map<String,Object> view(Map<String,Object> row) {
        Map<String,Object> view=new LinkedHashMap<>();
        for(String key:List.of("id","snapshot_id","status","last_error_code","created_at","finished_at","agent_task_id")) {
            Object value=row.get(key); view.put(key,value instanceof Timestamp stamp?stamp.toInstant().toString():value);
        }
        view.put("question",Json.object((String)row.get("input_json")).get("question"));
        view.put("poll_url","/api/v1/agent-tasks/"+row.get("agent_task_id"));
        view.put("result",row.get("result_json")==null?null:Json.object((String)row.get("result_json")));
        view.put("informational_only",true); return view;
    }
}
