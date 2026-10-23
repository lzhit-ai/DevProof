package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Owns knowledge-base membership; parsing/embedding is deliberately outside this aggregate. */
@Service
public class KnowledgeBases {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    public KnowledgeBases(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit;
    }
    @Transactional public List<Map<String,Object>> all(UUID actor) {
        if(jdbc.queryForObject("SELECT count(*) FROM users WHERE id=? AND status='ACTIVE'",Integer.class,actor)==0)
            throw new ApiProblem(403,"AUTH_FORBIDDEN","账号当前无法访问知识库");
        return jdbc.queryForList("""
            SELECT k.* FROM knowledge_bases k WHERE EXISTS(
              SELECT 1 FROM projects p JOIN project_members m ON m.project_id=p.id
              WHERE p.deleted_at IS NULL AND m.user_id=? AND (p.id=k.project_id OR EXISTS(
                SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=p.id AND b.knowledge_base_id=k.id)))
            ORDER BY k.created_at,k.id
            """,actor).stream().map(KnowledgeBases::view).toList();
    }
    @Transactional public List<Map<String,Object>> list(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("SELECT k.* FROM knowledge_bases k JOIN project_knowledge_bases b ON b.knowledge_base_id=k.id WHERE b.project_id=? ORDER BY k.created_at,k.id",project)
            .stream().map(KnowledgeBases::view).toList();
    }
    @Transactional public CommandStore.Result create(UUID project,UUID actor,CommandStore.Context command,String name) {
        owners.requireJavaKnowledgeBases(); lockProject(project); access.require(project,actor,"SUBMITTER","ADMIN");
        String trimmed=UnicodeText.strip(name); if(trimmed.isEmpty())throw new ApiProblem(422,"INPUT_INVALID","知识库名称不能为空");
        return commands.execute(command,201,()-> {
            UUID id=UUID.randomUUID();
            jdbc.update("INSERT INTO knowledge_bases(id,project_id,name,created_by) VALUES(?,?,?,?)",id,project,trimmed,actor);
            jdbc.update("INSERT INTO project_knowledge_bases(id,project_id,knowledge_base_id,created_by) VALUES(?,?,?,?)",UUID.randomUUID(),project,id,actor);
            audit.append(project,actor,"KnowledgeBase",id,"KNOWLEDGE_BASE_CREATED",command.correlationId(),Map.of("name",trimmed),null,null);
            return view(jdbc.queryForMap("SELECT * FROM knowledge_bases WHERE id=?",id));
        });
    }
    @Transactional public CommandStore.Result mount(UUID project,UUID base,UUID actor,CommandStore.Context command) {
        owners.requireJavaKnowledgeBases(); lockProject(project); access.require(project,actor,"SUBMITTER","ADMIN");
        Map<String,Object> knowledge=accessible(base,actor);
        return commands.execute(command,201,()-> {
            int inserted=jdbc.update("INSERT INTO project_knowledge_bases(id,project_id,knowledge_base_id,created_by) VALUES(?,?,?,?) ON CONFLICT(project_id,knowledge_base_id) DO NOTHING",UUID.randomUUID(),project,base,actor);
            if(inserted==1)audit.append(project,actor,"KnowledgeBase",base,"KNOWLEDGE_BASE_MOUNTED",command.correlationId(),Map.of(),null,null);
            return view(knowledge);
        });
    }
    @Transactional public void unmount(UUID project,UUID base,UUID actor,String correlation) {
        owners.requireJavaKnowledgeBases(); lockProject(project); access.require(project,actor,"SUBMITTER","ADMIN");
        if(jdbc.update("DELETE FROM project_knowledge_bases WHERE project_id=? AND knowledge_base_id=?",project,base)==0)
            throw new ApiProblem(404,"RESOURCE_NOT_FOUND","项目未挂载该知识库");
        audit.append(project,actor,"KnowledgeBase",base,"KNOWLEDGE_BASE_UNMOUNTED",correlation,Map.of(),null,null);
    }
    private Map<String,Object> accessible(UUID base,UUID actor) {
        var rows=jdbc.queryForList("SELECT * FROM knowledge_bases WHERE id=? FOR SHARE",base);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","知识库不存在");
        var projects=jdbc.queryForList("""
            SELECT p.id FROM projects p JOIN project_members m ON m.project_id=p.id JOIN users u ON u.id=m.user_id
            WHERE p.deleted_at IS NULL AND m.user_id=? AND u.status='ACTIVE'
              AND (p.id=? OR EXISTS(SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=p.id AND b.knowledge_base_id=?))
            ORDER BY p.id LIMIT 1 FOR SHARE OF p
            """,actor,rows.getFirst().get("project_id"),base);
        if(projects.isEmpty())throw new ApiProblem(403,"AUTH_FORBIDDEN","当前用户无法访问该知识库");
        return rows.getFirst();
    }
    private void lockProject(UUID project) {
        if(jdbc.queryForList("SELECT id FROM projects WHERE id=? AND deleted_at IS NULL FOR UPDATE",project).isEmpty())
            throw new ApiProblem(404,"RESOURCE_NOT_FOUND","项目不存在");
    }
    private static Map<String,Object> view(Map<String,Object> row) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(String key:List.of("id","project_id","name","created_at","updated_at")) {
            Object value=row.get(key); result.put(key,value instanceof Timestamp time?time.toInstant().toString():value);
        }
        return result;
    }
}
