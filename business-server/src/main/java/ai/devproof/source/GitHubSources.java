package ai.devproof.source;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GitHubSources {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    public GitHubSources(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit;
    }
    @Transactional public List<Map<String,Object>> connections(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("SELECT * FROM external_connections WHERE project_id=? ORDER BY created_at,id",project).stream().map(SourceViews::connection).toList();
    }
    @Transactional public CommandStore.Result create(UUID project,UUID actor,CommandStore.Context command,String provider,String name,String repository,String secret) {
        access.require(project,actor,"ADMIN"); owners.requireJavaGitHubSources();
        if(!provider.equals("GITHUB"))throw ApiInput.invalid(); String normalized=UnicodeText.strip(name),slug=UnicodeText.strip(repository).replaceAll("^/+|/+$","");
        String ref=secret==null || UnicodeText.strip(secret).isEmpty()?null:UnicodeText.strip(secret);
        if(normalized.isEmpty() || !slug.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+") || ref!=null && !ref.matches("[A-Z][A-Z0-9_]{2,159}"))throw ApiInput.invalid();
        return commands.execute(command,201,()-> {
            jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(CAST(? AS text),91))",Object.class,project+":"+slug);
            var previous=jdbc.queryForList("SELECT * FROM external_connections WHERE project_id=? AND provider='GITHUB' AND repository_slug=? FOR UPDATE",project,slug);
            UUID id;
            if(previous.isEmpty()) {
                id=UUID.randomUUID(); jdbc.update("INSERT INTO external_connections(id,project_id,provider,name,repository_slug,api_base_url,secret_ref,is_active,created_by) VALUES(?,?,'GITHUB',?,?,'https://api.github.com',?,true,?)",id,project,normalized,slug,ref,actor);
                audit.append(project,actor,"ExternalConnection",id,"EXTERNAL_CONNECTION_CREATED",command.correlationId(),Map.of("provider","GITHUB","repositorySlug",slug),null,null);
            } else {
                Map<String,Object> existing=previous.getFirst(); id=(UUID)existing.get("id");
                if(!Objects.equals(ref,existing.get("secret_ref"))) {
                    jdbc.update("UPDATE external_connections SET secret_ref=?,updated_at=clock_timestamp() WHERE id=?",ref,id);
                    audit.append(project,actor,"ExternalConnection",id,"EXTERNAL_CONNECTION_SECRET_REF_UPDATED",command.correlationId(),Map.of("secretRefConfigured",ref!=null),null,null);
                }
            }
            return SourceViews.connection(jdbc.queryForMap("SELECT * FROM external_connections WHERE id=?",id));
        });
    }
    @Transactional public CommandStore.Result queue(UUID project,UUID connection,UUID actor,CommandStore.Context command) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaGitHubSources();
        return commands.execute(command,200,()-> {
            var rows=jdbc.queryForList("SELECT * FROM external_connections WHERE id=? AND project_id=? FOR UPDATE",connection,project);
            if(rows.isEmpty())throw missing("外部来源连接不存在"); if(!Boolean.TRUE.equals(rows.getFirst().get("is_active")))throw new ApiProblem(409,"STATE_CONFLICT","外部来源连接已停用");
            var active=jdbc.queryForList("SELECT *,continuation_cursor::text AS cursor_json FROM source_sync_runs WHERE connection_id=? AND status='RUNNING' ORDER BY started_at DESC,id DESC LIMIT 1",connection);
            if(!active.isEmpty())return SourceViews.sync(active.getFirst());
            Map<String,Object> cursor=GitHubSourceClient.initialCursor((String)rows.getFirst().get("repository_slug"));
            var previous=jdbc.queryForList("SELECT status,continuation_cursor::text AS cursor_json FROM source_sync_runs WHERE connection_id=? ORDER BY started_at DESC,id DESC LIMIT 1",connection);
            if(!previous.isEmpty() && Set.of("PARTIALLY_SUCCEEDED","FAILED").contains(previous.getFirst().get("status"))) {
                Map<String,Object> saved=Json.object((String)previous.getFirst().get("cursor_json"));
                if(GitHubSourceClient.resumable(saved))cursor=saved;
            }
            UUID id=UUID.randomUUID(); jdbc.update("INSERT INTO source_sync_runs(id,connection_id,requested_by,status,fetched_count,changed_count,page_count,continuation_cursor,attempt_no,max_attempts,executor_owner) VALUES(?,?,?,'RUNNING',0,0,0,CAST(? AS jsonb),0,3,'JAVA')",id,connection,actor,Json.write(cursor));
            audit.append(project,actor,"SourceSyncRun",id,"SOURCE_SYNC_QUEUED",command.correlationId(),Map.of("connectionId",connection.toString()),null,null);
            return SourceViews.sync(jdbc.queryForMap("SELECT *,continuation_cursor::text AS cursor_json FROM source_sync_runs WHERE id=?",id));
        });
    }
    @Transactional public List<Map<String,Object>> runs(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("SELECT r.*,r.continuation_cursor::text AS cursor_json FROM source_sync_runs r JOIN external_connections c ON c.id=r.connection_id WHERE c.project_id=? ORDER BY r.started_at DESC,r.id DESC LIMIT 50",project).stream().map(SourceViews::sync).toList();
    }
    @Transactional public List<Map<String,Object>> deliveries(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("""
            SELECT d.*,c.provider,c.repository_slug,r.resource_type,v.web_url,v.milestone_key,v.revision_no AS resource_revision,v.payload::text AS payload_json
            FROM delivery_items d JOIN external_resources r ON r.id=d.external_resource_id AND r.resource_type='PULL_REQUEST'
            JOIN external_connections c ON c.id=r.connection_id AND c.project_id=d.project_id
            LEFT JOIN LATERAL(SELECT web_url,milestone_key,revision_no,payload FROM external_resource_revisions WHERE resource_id=r.id ORDER BY revision_no DESC LIMIT 1)v ON true
            WHERE d.project_id=? ORDER BY d.source_updated_at DESC NULLS LAST,d.created_at DESC,d.id LIMIT 100
            """,project).stream().map(row-> {
                Map<String,Object> result=SourceViews.fields(row,"id","project_id","external_key","title","planning_status","verification_status","source_updated_at","provider","repository_slug","web_url","milestone_key","resource_revision","resource_type");
                Object payload=row.get("payload_json")==null?null:Json.read((String)row.get("payload_json")); result.put("pull_request",payload instanceof Map<?,?> map?map.get("pullRequest"):null); return result;
            }).toList();
    }
    @Transactional public List<Map<String,Object>> links(UUID project,UUID delivery,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); requireDelivery(project,delivery,false); return linkRows(delivery);
    }
    @Transactional public CommandStore.Result linkDocument(UUID project,UUID delivery,UUID actor,CommandStore.Context command,UUID source,String role) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaGitHubSources(); if(!Set.of("ACCEPTANCE","DESIGN","PLAN").contains(role))throw ApiInput.invalid();
        return commands.execute(command,201,()-> {
            requireDelivery(project,delivery,true);
            if(jdbc.queryForList("SELECT id FROM source_revisions WHERE id=? AND project_id=? AND processing_status='READY' FOR SHARE",source,project).isEmpty())throw new ApiProblem(422,"INPUT_INVALID","资料版本不存在、不属于当前项目或尚未完成处理");
            var existing=jdbc.queryForList("SELECT id FROM delivery_item_source_links WHERE delivery_item_id=? AND source_revision_id=? AND link_role=?",delivery,source,role);
            UUID id=existing.isEmpty()?UUID.randomUUID():(UUID)existing.getFirst().get("id");
            if(existing.isEmpty()) {
                jdbc.update("INSERT INTO delivery_item_source_links(id,delivery_item_id,source_revision_id,link_role,created_by) VALUES(?,?,?,?,?)",id,delivery,source,role,actor);
                audit.append(project,actor,"DeliveryItemSourceLink",id,"DELIVERY_ITEM_DOCUMENT_SOURCE_LINKED",command.correlationId(),Map.of("deliveryItemId",delivery.toString(),"sourceRevisionId",source.toString(),"linkRole",role),null,null);
            }
            return linkRows(delivery).stream().filter(item->id.equals(item.get("id"))).findFirst().orElseThrow(()->missing("资料关联不存在"));
        });
    }
    private void requireDelivery(UUID project,UUID id,boolean lock) {
        var rows=jdbc.queryForList("SELECT d.id FROM delivery_items d JOIN external_resources r ON r.id=d.external_resource_id WHERE d.id=? AND d.project_id=? AND r.resource_type='PULL_REQUEST'"+(lock?" FOR UPDATE OF d":""),id,project);
        if(rows.isEmpty())throw missing("代码交付不存在");
    }
    private List<Map<String,Object>> linkRows(UUID delivery) {
        return jdbc.queryForList("SELECT l.*,s.logical_name,s.revision_no,v.title FROM delivery_item_source_links l LEFT JOIN source_revisions s ON s.id=l.source_revision_id LEFT JOIN external_resource_revisions v ON v.id=l.external_resource_revision_id WHERE l.delivery_item_id=? ORDER BY l.created_at,l.id",delivery).stream().map(row-> {
            boolean document=row.get("source_revision_id")!=null;
            return Map.<String,Object>of("id",row.get("id"),"delivery_item_id",row.get("delivery_item_id"),"source_kind",document?"DOCUMENT":"EXTERNAL_RESOURCE","source_id",row.get(document?"source_revision_id":"external_resource_revision_id"),
                "source_label",document?row.get("logical_name")==null?"资料版本不可用":row.get("logical_name")+" r"+row.get("revision_no"):Objects.toString(row.get("title"),"外部来源版本不可用"),"link_role",row.get("link_role"));
        }).toList();
    }
    private ApiProblem missing(String text) { return new ApiProblem(404,"RESOURCE_NOT_FOUND",text); }
}
