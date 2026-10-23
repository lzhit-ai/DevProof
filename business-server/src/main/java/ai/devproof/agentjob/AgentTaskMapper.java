package ai.devproof.agentjob;

import java.sql.Timestamp;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.*;

@Mapper
public interface AgentTaskMapper {
    @Select(value="""
        WITH expired AS (
          UPDATE agent_tasks t SET status='FAILED',last_error_code='MAX_ATTEMPTS_EXCEEDED',finished_at=clock_timestamp()
          FROM agent_task_attempts a WHERE a.id=t.current_attempt_id AND t.status='RUNNING'
            AND a.lease_expires_at<clock_timestamp() AND t.attempt_no>=t.max_attempts
          RETURNING t.*
        ), attempts AS (
          UPDATE agent_task_attempts a SET status='EXPIRED' FROM expired e WHERE a.id=e.current_attempt_id
        ), planning AS (
          UPDATE planning_runs r SET status='FAILED',finished_at=clock_timestamp() FROM expired e WHERE r.id=e.planning_run_id
        ) SELECT * FROM expired
        """,affectData=true)
    List<Map<String,Object>> expireExhausted();
    @Select("SELECT clock_timestamp()") Timestamp now();
    @Select("SELECT * FROM agent_tasks WHERE id=#{id} FOR UPDATE") Map<String,Object> lock(UUID id);
    @Select("SELECT * FROM agent_task_attempts WHERE id=#{id}") Map<String,Object> attempt(UUID id);
    @Select("""
        SELECT t.* FROM agent_tasks t LEFT JOIN agent_task_attempts a ON a.id=t.current_attempt_id
        JOIN projects p ON p.id=t.project_id AND p.deleted_at IS NULL
        WHERE t.executor_version=#{executorVersion} AND t.task_kind=ANY(string_to_array(#{kinds},','))
          AND t.attempt_no<t.max_attempts AND t.cancel_requested_at IS NULL
          AND ((t.status='QUEUED' AND t.available_at<=clock_timestamp()) OR (t.status='RUNNING' AND a.lease_expires_at<clock_timestamp()))
        ORDER BY t.available_at,t.created_at FOR UPDATE OF t SKIP LOCKED LIMIT 1
        """)
    Map<String,Object> claim(String executorVersion, String kinds);
    @Update("UPDATE agent_task_attempts SET status='EXPIRED' WHERE id=#{id} AND status='RUNNING'")
    void expire(UUID id);
    @Insert("""
        INSERT INTO agent_task_attempts(id,task_id,worker_id,fencing_token,status,lease_expires_at)
        VALUES(#{attemptId},#{taskId},#{workerId},#{fence},'RUNNING',clock_timestamp()+make_interval(secs=>#{leaseSeconds}))
        """)
    void begin(UUID taskId, UUID attemptId, String workerId, long fence, int leaseSeconds);
    @Update("UPDATE agent_tasks SET status='RUNNING',attempt_no=attempt_no+1,fencing_token=#{fence},current_attempt_id=#{attemptId} WHERE id=#{taskId}")
    void claimed(UUID taskId, UUID attemptId, long fence);
    @Update("UPDATE agent_task_attempts SET heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+make_interval(secs=>#{leaseSeconds}) WHERE id=#{attemptId}")
    void heartbeat(UUID attemptId, int leaseSeconds);
    @Update("UPDATE agent_task_attempts SET status=#{status} WHERE id=#{attemptId}")
    void attemptStatus(UUID attemptId, String status);
    @Update("UPDATE agent_tasks SET status='SUCCEEDED',accepted_hash=#{hash},accepted_json=#{json},finished_at=clock_timestamp() WHERE id=#{id}")
    void complete(UUID id, String hash, String json);
    @Update("""
        UPDATE agent_tasks SET status=#{status},last_error_code=#{errorCode},available_at=clock_timestamp()+make_interval(secs=>#{delay}),
        finished_at=CASE WHEN #{status}='QUEUED' THEN NULL ELSE clock_timestamp() END WHERE id=#{id}
        """)
    void fail(UUID id, String status, String errorCode, int delay);
    @Insert("""
        INSERT INTO agent_task_events(task_id,attempt_id,event_seq,event_json) VALUES(#{taskId},#{attemptId},#{seq},#{json})
        ON CONFLICT(task_id,attempt_id,event_seq) DO NOTHING
        """)
    int event(UUID taskId, UUID attemptId, long seq, String json);
    @Select("SELECT event_json FROM agent_task_events WHERE task_id=#{taskId} AND attempt_id=#{attemptId} AND event_seq=#{seq}")
    String eventBody(UUID taskId, UUID attemptId, long seq);
    @Select("SELECT * FROM agent_tasks WHERE id=#{id}") Map<String,Object> get(UUID id);
    @Select("SELECT event_json FROM agent_task_events WHERE task_id=#{taskId} AND attempt_id=#{attemptId} AND event_seq>#{after} ORDER BY event_seq LIMIT 200")
    List<String> events(UUID taskId, UUID attemptId, long after);
    @Update("UPDATE agent_tasks SET cancel_requested_at=clock_timestamp(),status='CANCELLED',finished_at=clock_timestamp() WHERE id=#{id}")
    void cancel(UUID id);
    @Select("SELECT count(*) FROM project_members m JOIN projects p ON p.id=m.project_id AND p.deleted_at IS NULL JOIN users u ON u.id=m.user_id AND u.status='ACTIVE' WHERE m.project_id=#{projectId} AND m.user_id=#{actorId}")
    int currentAuthorization(UUID projectId, UUID actorId);
    @Insert("""
        INSERT INTO agent_tasks(id,project_id,created_by,analysis_run_id,planning_run_id,claim_proposal_run_id,question_run_id,task_kind,executor_version,payload_json,max_attempts)
        VALUES(#{id},#{projectId},#{actorId},#{analysisId},#{planningId},#{claimId},#{questionId},#{kind},#{executor},#{payload},#{maxAttempts})
        """)
    void enqueue(UUID id, UUID projectId, UUID actorId, UUID analysisId, UUID planningId, UUID claimId, UUID questionId, String kind, String executor, String payload, int maxAttempts);
    @Update("UPDATE planning_runs SET status=#{status},finished_at=CASE WHEN #{status} IN ('QUEUED','RUNNING') THEN NULL ELSE clock_timestamp() END WHERE id=#{id}")
    void planningStatus(UUID id,String status);
}
