package ai.devproof.planning;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.*;

@Mapper
public interface PlanningMapper {
    @Select("SELECT id,display_url,credential_ref FROM git_repositories WHERE project_id=#{projectId} ORDER BY created_at")
    List<Map<String,Object>> repositories(UUID projectId);
    @Select("SELECT * FROM git_repositories WHERE id=#{id} AND project_id=#{projectId}")
    Map<String,Object> repository(UUID projectId, UUID id);
    @Insert("INSERT INTO repository_snapshots(id,project_id,repository_id,target_sha,content_hash,body_json,created_by) VALUES(#{id},#{projectId},#{repositoryId},#{sha},#{hash},#{body},#{actorId})")
    void snapshot(UUID id, UUID projectId, UUID repositoryId, String sha, String hash, String body, UUID actorId);
    @Select("SELECT id,repository_id,target_sha,content_hash,created_at FROM repository_snapshots WHERE project_id=#{projectId} ORDER BY created_at DESC LIMIT 50")
    List<Map<String,Object>> snapshots(UUID projectId);
    @Select("SELECT * FROM repository_snapshots WHERE id=#{id} AND project_id=#{projectId}")
    Map<String,Object> snapshotById(UUID projectId, UUID id);
    @Select("SELECT * FROM ideas WHERE project_id=#{projectId} ORDER BY created_at DESC LIMIT 100")
    List<Map<String,Object>> ideas(UUID projectId);
    @Select("SELECT * FROM ideas WHERE id=#{id} AND project_id=#{projectId} FOR UPDATE")
    Map<String,Object> lockIdea(UUID projectId, UUID id);
    @Select("SELECT * FROM ideas WHERE id=#{id} AND project_id=#{projectId}")
    Map<String,Object> idea(UUID projectId, UUID id);
    @Insert("INSERT INTO ideas(id,project_id,title,created_by) VALUES(#{id},#{projectId},#{title},#{actorId})")
    void createIdea(UUID id, UUID projectId, String title, UUID actorId);
    @Update("UPDATE ideas SET title=#{title},version=version+1 WHERE id=#{id}")
    void reviseIdea(UUID id, String title);
    @Insert("INSERT INTO idea_revisions(id,idea_id,revision_no,content,created_by) VALUES(#{id},#{ideaId},#{number},#{content},#{actorId})")
    void revision(UUID id, UUID ideaId, int number, String content, UUID actorId);
    @Select("SELECT * FROM idea_revisions WHERE idea_id=#{ideaId} ORDER BY revision_no DESC LIMIT 1")
    Map<String,Object> latestRevision(UUID ideaId);
    @Select("SELECT * FROM idea_revisions WHERE id=#{id}")
    Map<String,Object> revisionById(UUID id);
    @Select("SELECT * FROM planning_runs WHERE idea_revision_id=#{revisionId} ORDER BY created_at DESC LIMIT 1")
    Map<String,Object> latestRun(UUID revisionId);
    @Select("SELECT t.id,t.status,t.last_error_code FROM agent_tasks t WHERE t.planning_run_id=#{runId}")
    Map<String,Object> taskForRun(UUID runId);
    @Select("SELECT q.* FROM planning_questions q JOIN planning_runs r ON r.id=q.planning_run_id WHERE r.idea_revision_id=#{revisionId} ORDER BY q.created_at,q.id")
    List<Map<String,Object>> questions(UUID revisionId);
    @Update("UPDATE planning_questions SET answer=#{answer},answered_by=#{actorId},answered_at=clock_timestamp() WHERE id=#{id} AND planning_run_id=#{runId} AND answer IS NULL")
    int answer(UUID id, UUID runId, String answer, UUID actorId);
    @Insert("INSERT INTO planning_input_snapshots(id,project_id,repository_snapshot_id,content_hash,input_json,created_by) VALUES(#{id},#{projectId},#{repositorySnapshotId},#{hash},#{json},#{actorId})")
    void input(UUID id, UUID projectId, UUID repositorySnapshotId, String hash, String json, UUID actorId);
    @Insert("INSERT INTO planning_runs(id,project_id,snapshot_id,idea_revision_id,status,created_by,request_key,request_hash) VALUES(#{id},#{projectId},#{snapshotId},#{revisionId},'QUEUED',#{actorId},#{requestKey},#{requestHash})")
    void run(UUID id, UUID projectId, UUID snapshotId, UUID revisionId, UUID actorId, String requestKey, String requestHash);
    @Select("SELECT * FROM planning_runs WHERE project_id=#{projectId} AND created_by=#{actorId} AND request_key=#{key}")
    Map<String,Object> byRequest(UUID projectId, UUID actorId, String key);
    @Select("SELECT * FROM planning_input_snapshots WHERE id=#{id}")
    Map<String,Object> inputById(UUID id);
    @Select("SELECT * FROM planning_runs WHERE id=#{id}")
    Map<String,Object> runById(UUID id);
    @Update("UPDATE planning_runs SET status='SUCCEEDED',finished_at=clock_timestamp() WHERE id=#{id}")
    void succeeded(UUID id);
    @Insert("INSERT INTO planning_questions(id,planning_run_id,question_key,question,reason) VALUES(#{id},#{runId},#{key},#{question},#{reason})")
    void question(UUID id, UUID runId, String key, String question, String reason);
    @Select("SELECT coalesce(max(sequence_no),0)+1 FROM plan_versions WHERE idea_revision_id=#{revisionId}")
    int nextPlanSequence(UUID revisionId);
    @Insert("INSERT INTO plan_versions(id,idea_revision_id,planning_run_id,sequence_no,parent_plan_id,body_json,content_hash,created_by) VALUES(#{id},#{revisionId},#{runId},#{sequence},#{parentId},#{body},#{hash},#{actorId})")
    void plan(UUID id, UUID revisionId, UUID runId, int sequence, UUID parentId, String body, String hash, UUID actorId);
    @Select("SELECT v.*,i.idea_id,i.revision_no AS idea_revision_no,rs.repository_id,rs.target_sha FROM plan_versions v JOIN idea_revisions i ON i.id=v.idea_revision_id JOIN planning_runs pr ON pr.id=v.planning_run_id JOIN planning_input_snapshots ps ON ps.id=pr.snapshot_id JOIN repository_snapshots rs ON rs.id=ps.repository_snapshot_id WHERE i.idea_id=#{ideaId} ORDER BY i.revision_no DESC,v.sequence_no DESC")
    List<Map<String,Object>> plans(UUID ideaId);
    @Select("SELECT v.*,r.idea_id,i.project_id,r.revision_no AS idea_revision_no,rs.repository_id,rs.target_sha FROM plan_versions v JOIN idea_revisions r ON r.id=v.idea_revision_id JOIN ideas i ON i.id=r.idea_id JOIN planning_runs pr ON pr.id=v.planning_run_id JOIN planning_input_snapshots ps ON ps.id=pr.snapshot_id JOIN repository_snapshots rs ON rs.id=ps.repository_snapshot_id WHERE v.id=#{id} FOR UPDATE OF v")
    Map<String,Object> lockPlan(UUID id);
    @Select("SELECT v.*,r.idea_id,i.project_id,r.revision_no AS idea_revision_no,rs.repository_id,rs.target_sha FROM plan_versions v JOIN idea_revisions r ON r.id=v.idea_revision_id JOIN ideas i ON i.id=r.idea_id JOIN planning_runs pr ON pr.id=v.planning_run_id JOIN planning_input_snapshots ps ON ps.id=pr.snapshot_id JOIN repository_snapshots rs ON rs.id=ps.repository_snapshot_id WHERE v.id=#{id}")
    Map<String,Object> planContext(UUID id);
    @Update("UPDATE plan_versions SET body_json=#{body},content_hash=#{hash},version=version+1 WHERE id=#{id}")
    void editPlan(UUID id, String body, String hash);
    @Update("UPDATE plan_versions SET status='SUPERSEDED' WHERE status='CONFIRMED' AND idea_revision_id IN (SELECT id FROM idea_revisions WHERE idea_id=#{ideaId})")
    void supersede(UUID ideaId);
    @Update("UPDATE plan_versions SET status='CONFIRMED',confirmed_by=#{actorId},confirmed_at=clock_timestamp() WHERE id=#{id}")
    void confirm(UUID id, UUID actorId);
}
