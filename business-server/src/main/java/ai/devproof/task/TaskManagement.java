package ai.devproof.task;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.verification.VerificationOrchestration;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskManagement {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final VerificationOrchestration orchestration;
    public TaskManagement(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit,VerificationOrchestration orchestration) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit; this.orchestration=orchestration;
    }
    @Transactional public List<Map<String,Object>> list(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("""
            SELECT t.id,t.project_id,t.delivery_item_id,t.title,t.requirement_key,t.created_at,t.updated_at,
              c.id AS cycle_id,coalesce(c.business_status,'UNKNOWN') AS cycle_status,
              s.id AS formal_snapshot_id,s.snapshot_hash AS formal_snapshot_hash,
              report.id AS report_id,report.status AS report_status,p.id AS published_record_id,
              r.resource_type,revision.payload::text AS revision_payload
            FROM verification_tasks t
            LEFT JOIN delivery_items item ON item.id=t.delivery_item_id
            LEFT JOIN external_resources r ON r.id=item.external_resource_id
            LEFT JOIN LATERAL(SELECT payload FROM external_resource_revisions WHERE resource_id=r.id ORDER BY revision_no DESC LIMIT 1) revision ON true
            LEFT JOIN LATERAL(SELECT id,business_status FROM verification_cycles WHERE task_id=t.id ORDER BY sequence_no DESC LIMIT 1) c ON true
            LEFT JOIN LATERAL(SELECT id,snapshot_hash FROM input_snapshots WHERE cycle_id=c.id AND purpose='FORMAL' ORDER BY created_at DESC,id DESC LIMIT 1) s ON true
            LEFT JOIN LATERAL(SELECT id,status FROM report_versions WHERE cycle_id=c.id ORDER BY sequence_no DESC LIMIT 1) report ON true
            LEFT JOIN published_records p ON p.report_version_id=report.id
            WHERE t.project_id=? ORDER BY t.updated_at DESC,t.created_at DESC,t.id LIMIT 100
            """,project).stream().map(row-> {
                Map<String,Object> result=new LinkedHashMap<>(row); Object payload=row.get("revision_payload")==null?null:Json.read((String)row.get("revision_payload"));
                result.remove("revision_payload"); result.remove("resource_type");
                result.put("delivery_pull_request","PULL_REQUEST".equals(row.get("resource_type")) && payload instanceof Map<?,?> map && map.get("pullRequest") instanceof Map<?,?>?((Map<?,?>)payload).get("pullRequest"):null);
                for(String key:List.of("created_at","updated_at"))result.put(key,((Timestamp)row.get(key)).toInstant().toString());
                return result;
            }).toList();
    }
    @Transactional public CommandStore.Result create(UUID project,UUID actor,CommandStore.Context command,String title,String requirement,UUID delivery,UUID template) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaTaskManagement();
        return commands.execute(command,201,()-> {
            requireDelivery(project,delivery); UUID task=UUID.randomUUID(),cycle=UUID.randomUUID();
            if(jdbc.update("INSERT INTO verification_tasks(id,project_id,delivery_item_id,title,requirement_key,created_by,version) VALUES(?,?,?,?,?,?,1) ON CONFLICT(project_id,requirement_key) DO NOTHING",task,project,delivery,title,requirement,actor)==0)throw state("项目内需求标识已存在");
            jdbc.update("INSERT INTO verification_cycles(id,task_id,sequence_no,business_status,version) VALUES(?,?,1,'DRAFT',1)",cycle,task);
            orchestration.bindNewTask(task,project,actor,template);
            audit.append(project,actor,"VerificationTask",task,"VERIFICATION_TASK_CREATED",command.correlationId(),Map.of("cycleId",cycle.toString(),"deliveryItemId",delivery.toString()),null,1);
            return response(task);
        });
    }
    @Transactional public CommandStore.Result nextCycle(UUID project,UUID task,UUID actor,CommandStore.Context command) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaTaskManagement();
        return commands.execute(command,201,()-> {
            lock(project,task); var cycles=jdbc.queryForList("SELECT * FROM verification_cycles WHERE task_id=? ORDER BY sequence_no DESC LIMIT 1 FOR UPDATE",task);
            if(cycles.isEmpty() || !"PUBLISHED".equals(cycles.getFirst().get("business_status")))throw state("仅已发布核验轮次可以创建新版本");
            Map<String,Object> previous=cycles.getFirst(); UUID cycle=UUID.randomUUID(); int sequence=((Number)previous.get("sequence_no")).intValue()+1;
            jdbc.update("INSERT INTO verification_cycles(id,task_id,sequence_no,business_status,created_from_cycle_id,version) VALUES(?,?,?,'DRAFT',?,1)",cycle,task,sequence,previous.get("id"));
            audit.append(project,actor,"VerificationCycle",cycle,"VERIFICATION_CYCLE_CREATED",command.correlationId(),Map.of("previousCycleId",previous.get("id").toString()),null,null);
            return Map.of("id",cycle.toString(),"taskId",task.toString(),"sequenceNo",sequence,"status","DRAFT");
        });
    }
    @Transactional public CommandStore.Result bindDelivery(UUID project,UUID task,UUID actor,CommandStore.Context command,UUID delivery) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaTaskManagement();
        return commands.execute(command,200,()-> {
            Map<String,Object> row=lock(project,task), item=requireDelivery(project,delivery);
            if(!delivery.equals(row.get("delivery_item_id")) && jdbc.queryForObject("SELECT count(*) FROM published_records WHERE task_id=?",Integer.class,task)>0)throw state("已有正式记录的历史任务不能更换交付归属");
            for(Map<String,Object> git:jdbc.queryForList("SELECT r.display_url FROM git_snapshots g JOIN verification_cycles c ON c.id=g.cycle_id LEFT JOIN git_repositories r ON r.id=g.repository_id WHERE c.task_id=?",task)) {
                String slug=repositorySlug(git.get("display_url"));
                if(slug==null || !slug.equals(item.get("repository_slug").toString().toLowerCase(Locale.ROOT)))throw new ApiProblem(422,"INPUT_INVALID","交付事项与任务已有 Git 范围不属于同一来源仓库");
            }
            jdbc.update("UPDATE verification_tasks SET delivery_item_id=?,version=version+1,updated_at=clock_timestamp() WHERE id=?",delivery,task);
            audit.append(project,actor,"VerificationTask",task,"TASK_DELIVERY_ITEM_BOUND",command.correlationId(),Map.of("deliveryItemId",delivery.toString()),null,((Number)row.get("version")).intValue()+1);
            return response(task);
        });
    }
    private Map<String,Object> requireDelivery(UUID project,UUID delivery) {
        var rows=jdbc.queryForList("SELECT d.*,r.resource_type,c.repository_slug,c.project_id AS source_project FROM delivery_items d JOIN external_resources r ON r.id=d.external_resource_id JOIN external_connections c ON c.id=r.connection_id WHERE d.id=? AND d.project_id=?",delivery,project);
        if(rows.isEmpty() || !"PULL_REQUEST".equals(rows.getFirst().get("resource_type")) || !project.equals(rows.getFirst().get("source_project")))throw new ApiProblem(422,"INPUT_INVALID","审查任务必须绑定当前项目已同步的 GitHub PR"); return rows.getFirst();
    }
    private Map<String,Object> lock(UUID project,UUID task) {
        var rows=jdbc.queryForList("SELECT * FROM verification_tasks WHERE id=? AND project_id=? FOR UPDATE",task,project);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","核验任务不存在"); return rows.getFirst();
    }
    private Map<String,Object> response(UUID task) {
        var row=jdbc.queryForMap("SELECT t.id,t.project_id,t.delivery_item_id,t.title,t.requirement_key,t.version,c.id AS cycle_id,c.business_status AS cycle_status FROM verification_tasks t JOIN LATERAL(SELECT id,business_status FROM verification_cycles WHERE task_id=t.id ORDER BY sequence_no DESC LIMIT 1)c ON true WHERE t.id=?",task);
        return new LinkedHashMap<>(row);
    }
    private String repositorySlug(Object raw) {
        return raw instanceof String value?RepositoryIdentity.githubSlug(value):null;
    }
    private ApiProblem state(String message) { return new ApiProblem(409,"STATE_CONFLICT",message); }
}
