package ai.devproof.project;

import ai.devproof.infrastructure.*;
import ai.devproof.source.ProjectSources;
import ai.devproof.verification.VerificationOrchestration;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.dao.CannotAcquireLockException;

@Service
public class ProjectManagement {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final ProjectSources sources;
    private final VerificationOrchestration orchestration;
    public ProjectManagement(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit,ProjectSources sources,VerificationOrchestration orchestration) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit; this.sources=sources; this.orchestration=orchestration;
    }
    @Transactional public List<Map<String,Object>> list(UUID actor) {
        return jdbc.queryForList("SELECT p.*,m.role FROM projects p JOIN project_members m ON m.project_id=p.id WHERE m.user_id=? AND p.deleted_at IS NULL ORDER BY p.updated_at DESC,p.created_at DESC,p.id",actor).stream().map(this::response).toList();
    }
    @Transactional public Map<String,Object> get(UUID project,UUID actor) {
        var rows=jdbc.queryForList("SELECT p.*,m.role FROM projects p JOIN project_members m ON m.project_id=p.id WHERE p.id=? AND m.user_id=? AND p.deleted_at IS NULL",project,actor);
        if(rows.isEmpty())throw missing(); return response(rows.getFirst());
    }
    @Transactional public CommandStore.Result create(UUID actor,CommandStore.Context command,String name,String description,String repository,List<UUID> bases) {
        if(jdbc.queryForList("SELECT id FROM users WHERE id=? AND status='ACTIVE' FOR SHARE",actor).isEmpty())throw new ApiProblem(401,"AUTH_INVALID","用户不可用");
        owners.requireJavaProjects();
        return commands.execute(command,201,()-> {
            UUID project=UUID.randomUUID();
            jdbc.update("INSERT INTO projects(id,name,description,owner_id,version) VALUES(?,?,?,?,1)",project,name,description,actor);
            jdbc.update("INSERT INTO project_members(id,project_id,user_id,role) VALUES(?,?,?,'ADMIN')",UUID.randomUUID(),project,actor);
            orchestration.ensureProject(project,actor);
            if(repository!=null && !repository.isEmpty())sources.initializeRepository(project,actor,repository,command.correlationId());
            sources.mount(project,actor,bases);
            audit.append(project,actor,"Project",project,"PROJECT_CREATED",command.correlationId(),Map.of(),null,1);
            return get(project,actor);
        });
    }
    @Transactional public CommandStore.Result addMember(UUID project,UUID actor,CommandStore.Context command,UUID user,String email,String role) {
        access.require(project,actor,"ADMIN"); owners.requireJavaProjects();
        if((user==null)==(email==null) || !Set.of("SUBMITTER","REVIEWER","ADMIN").contains(role))throw ApiInput.invalid();
        return commands.execute(command,201,()-> {
            var users=email==null?jdbc.queryForList("SELECT id FROM users WHERE id=?",user):jdbc.queryForList("SELECT id FROM users WHERE email=?",UnicodeText.strip(email).toLowerCase(Locale.ROOT));
            if(users.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","待添加用户不存在");
            UUID member=UUID.randomUUID(),target=(UUID)users.getFirst().get("id");
            if(jdbc.update("INSERT INTO project_members(id,project_id,user_id,role) VALUES(?,?,?,?) ON CONFLICT(project_id,user_id) DO NOTHING",member,project,target,role)==0)throw new ApiProblem(409,"STATE_CONFLICT","用户已是项目成员");
            audit.append(project,actor,"ProjectMember",member,"PROJECT_MEMBER_ADDED",command.correlationId(),Map.of("memberUserId",target.toString(),"role",role),null,null);
            return Map.of("id",member.toString(),"userId",target.toString(),"role",role);
        });
    }
    @Transactional public void delete(UUID project,UUID actor,String confirmation,String correlation) {
        owners.requireJavaProjects(); List<Map<String,Object>> rows;
        try { rows=jdbc.queryForList("SELECT p.*,m.role FROM projects p JOIN project_members m ON m.project_id=p.id WHERE p.id=? AND m.user_id=? FOR UPDATE OF p NOWAIT",project,actor); }
        catch(CannotAcquireLockException e) { throw new ApiProblem(409,"PROJECT_BUSY","项目仍有操作进行中，请稍后再删除"); }
        if(rows.isEmpty())throw missing(); Map<String,Object> row=rows.getFirst();
        if(!"ADMIN".equals(row.get("role")))throw new ApiProblem(403,"AUTH_FORBIDDEN","只有项目管理员可以删除项目");
        if(!confirmation.equals(row.get("name")))throw new ApiProblem(422,"INPUT_INVALID","请输入完整项目名称");
        if(row.get("deleted_at")!=null)return;
        if(busy(project))throw new ApiProblem(409,"PROJECT_BUSY","项目仍有待处理或运行中的任务，请等待结束后再删除");
        int version=((Number)row.get("version")).intValue();
        jdbc.update("UPDATE projects SET deleted_at=clock_timestamp(),version=version+1,updated_at=clock_timestamp() WHERE id=?",project);
        jdbc.update("UPDATE external_connections SET is_active=false,updated_at=clock_timestamp() WHERE project_id=?",project);
        audit.append(project,actor,"Project",project,"PROJECT_DELETED",correlation,Map.of("name",row.get("name")),version,version+1);
    }
    private boolean busy(UUID project) {
        return Boolean.TRUE.equals(jdbc.queryForObject("""
            SELECT EXISTS(SELECT 1 FROM analysis_runs r JOIN input_snapshots s ON s.id=r.snapshot_id JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE t.project_id=? AND (r.run_status IN ('QUEUED','RUNNING') OR EXISTS(SELECT 1 FROM analysis_jobs j WHERE j.run_id=r.id AND j.job_status IN ('QUEUED','RUNNING'))))
              OR EXISTS(SELECT 1 FROM source_sync_runs r JOIN external_connections c ON c.id=r.connection_id WHERE c.project_id=? AND r.status='RUNNING')
              OR EXISTS(SELECT 1 FROM source_ingestion_jobs j JOIN source_revisions s ON s.id=j.source_revision_id WHERE s.project_id=? AND j.job_status IN ('QUEUED','RUNNING'))
              OR EXISTS(SELECT 1 FROM retrieval_index_build_runs WHERE project_id=? AND status='RUNNING')
              OR EXISTS(SELECT 1 FROM agent_tasks WHERE project_id=? AND status IN ('QUEUED','RUNNING'))
              OR EXISTS(SELECT 1 FROM planning_runs WHERE project_id=? AND status IN ('QUEUED','RUNNING'))
            """,Boolean.class,project,project,project,project,project,project));
    }
    private Map<String,Object> response(Map<String,Object> row) {
        Map<String,Object> result=new LinkedHashMap<>(); result.put("id",row.get("id").toString()); result.put("name",row.get("name")); result.put("description",row.get("description"));
        result.put("version",row.get("version")); result.put("created_at",((Timestamp)row.get("created_at")).toInstant().toString()); result.put("can_delete","ADMIN".equals(row.get("role"))); return result;
    }
    private ApiProblem missing() { return new ApiProblem(404,"RESOURCE_NOT_FOUND","项目不存在或无法访问"); }
}
