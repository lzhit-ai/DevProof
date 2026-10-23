package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndexBuildStore {
    public record Product(UUID source,String normalizedHash,List<ComputeClient.Chunk> chunks) {}
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final SourceIndexWriter indexes;
    private final BusinessAudit audit;
    private final int maxAttempts;
    public IndexBuildStore(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,SourceIndexWriter indexes,
                           BusinessAudit audit,@Value("${JOB_MAX_ATTEMPTS:3}") int maxAttempts) {
        if(maxAttempts<1 || maxAttempts>10)throw new IllegalArgumentException("Invalid index build attempts");
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.indexes=indexes; this.audit=audit; this.maxAttempts=maxAttempts;
    }
    @Transactional public CommandStore.Result preflight(UUID project,UUID actor,CommandStore.Context command) {
        owners.requireJavaKnowledgeSources(); access.require(project,actor,"ADMIN"); return commands.replay(command);
    }
    @Transactional public CommandStore.Result enqueue(UUID project,UUID actor,CommandStore.Context command,ComputeClient.Configuration config) {
        owners.requireJavaKnowledgeSources(); jdbc.queryForList("SELECT id FROM projects WHERE id=? AND deleted_at IS NULL FOR UPDATE",project); access.require(project,actor,"ADMIN");
        return commands.execute(command,202,()-> {
            SourceIndexWriter.requireDimensions(jdbc,config.dimensions()); var manifest=sourceManifest(project);
            if(manifest.isEmpty())throw new ApiProblem(409,"SOURCE_NOT_READY","当前项目没有可重建索引的 READY 资料");
            UUID id=UUID.randomUUID();
            jdbc.update("""
                INSERT INTO retrieval_index_build_runs(id,project_id,target_index_version,status,source_count,reindexed_source_count,
                    reindexed_chunk_count,created_by,executor_owner,compute_configuration,configuration_hash,input_manifest,max_attempts)
                VALUES(?,?,?,'RUNNING',?,0,0,?,'JAVA',CAST(? AS jsonb),?,CAST(? AS jsonb),?)
                """,id,project,config.indexVersion(),manifest.size(),actor,Json.canonical(config.body()),config.hash(),Json.canonical(manifest),maxAttempts);
            audit.append(project,actor,"RetrievalIndexBuildRun",id,"RETRIEVAL_INDEX_BUILD_QUEUED",command.correlationId(),
                Map.of("targetIndexVersion",config.indexVersion(),"sourceCount",manifest.size()),null,null);
            return Map.of("build_run_id",id,"status","RUNNING","target_index_version",config.indexVersion());
        });
    }
    @Transactional public List<Map<String,Object>> list(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("""
            SELECT i.*,(SELECT count(*) FROM source_revisions s WHERE s.project_id=i.project_id AND s.processing_status='READY') AS ready_source_count,
              (SELECT count(DISTINCT s.id) FROM source_revisions s JOIN document_chunks c ON c.source_revision_id=s.id
                  WHERE s.project_id=i.project_id AND s.processing_status='READY' AND c.index_version=i.index_version) AS indexed_source_count,
              (SELECT count(*) FROM source_revisions s JOIN document_chunks c ON c.source_revision_id=s.id
                  WHERE s.project_id=i.project_id AND c.index_version=i.index_version) AS indexed_chunk_count
            FROM project_retrieval_indexes i WHERE i.project_id=? ORDER BY i.created_at,i.id
            """,project).stream().map(row->KnowledgeViews.fields(row,"id","project_id","index_version","parser_version","embedding_provider","embedding_model","dimensions","status","ready_source_count","indexed_source_count","indexed_chunk_count","activated_at","created_at")).toList();
    }
    @Transactional public List<Map<String,Object>> runs(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("SELECT * FROM retrieval_index_build_runs WHERE project_id=? ORDER BY started_at DESC,id LIMIT 50",project).stream()
            .map(row->KnowledgeViews.fields(row,"id","project_id","target_index_version","status","started_at","finished_at","source_count","reindexed_source_count","reindexed_chunk_count","error_code","error_message")).toList();
    }
    @Transactional public Map<String,Object> claim(String worker,int lease) {
        if(!owners.knowledgeSourcesAreJava())return null; owners.requireJavaKnowledgeSources();
        // Failure cleanup changes only run state, never source/index facts.
        jdbc.update("WITH expired AS (SELECT id FROM retrieval_index_build_runs WHERE executor_owner='JAVA' AND status='RUNNING' AND attempt_no>=max_attempts AND lease_expires_at<clock_timestamp() FOR UPDATE SKIP LOCKED) UPDATE retrieval_index_build_runs SET status='FAILED',error_code='MAX_ATTEMPTS_EXCEEDED',error_message='索引重建租约过期且尝试次数耗尽',finished_at=clock_timestamp(),lease_owner=NULL,lease_expires_at=NULL WHERE id IN (SELECT id FROM expired)");
        var rows=jdbc.queryForList("""
            SELECT * FROM retrieval_index_build_runs WHERE executor_owner='JAVA' AND status='RUNNING' AND attempt_no<max_attempts
              AND (available_at IS NULL OR available_at<=clock_timestamp())
              AND (lease_owner IS NULL OR lease_expires_at<clock_timestamp()) ORDER BY started_at,id FOR UPDATE SKIP LOCKED LIMIT 1
            """);
        if(rows.isEmpty())return null; var row=rows.getFirst(); int attempt=((Number)row.get("attempt_no")).intValue()+1;
        jdbc.update("UPDATE retrieval_index_build_runs SET attempt_no=?,lease_owner=?,lease_expires_at=clock_timestamp()+make_interval(secs=>?),heartbeat_at=clock_timestamp(),available_at=NULL WHERE id=?",attempt,worker,lease,row.get("id"));
        row.put("attempt_no",attempt); return row;
    }
    @Transactional public Map<String,Object> prepare(UUID id,String worker,int attempt) {
        owners.requireJavaKnowledgeSources(); var run=locked(id); if(!current(run,worker,attempt))return null;
        access.require((UUID)run.get("project_id"),(UUID)run.get("created_by"),"ADMIN"); return run;
    }
    @Transactional public List<Map<String,Object>> existing(UUID id,String worker,int attempt,UUID source) {
        var run=prepare(id,worker,attempt); if(run==null)throw new ApiProblem(409,"LEASE_EXPIRED","索引重建执行已失效");
        if(manifest(run).stream().noneMatch(row->source.toString().equals(row.get("id"))))throw new ApiProblem(409,"SOURCE_SCOPE_INVALID","资料不属于本次冻结重建范围");
        return jdbc.queryForList("SELECT chunk_index,content,text_hash,locator::text AS locator_json,embedding IS NOT NULL AS has_embedding FROM document_chunks WHERE source_revision_id=? AND index_version=? ORDER BY chunk_index",source,run.get("target_index_version"));
    }
    @Transactional public boolean heartbeat(UUID id,String worker,int attempt,int lease) {
        if(!owners.knowledgeSourcesAreJava())return false; owners.requireJavaKnowledgeSources();
        return jdbc.update("UPDATE retrieval_index_build_runs SET heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+make_interval(secs=>?) WHERE id=? AND status='RUNNING' AND lease_owner=? AND attempt_no=? AND lease_expires_at>clock_timestamp()",lease,id,worker,attempt)==1;
    }
    @Transactional public boolean complete(UUID id,String worker,int attempt,List<Product> products,ComputeClient.Configuration config) {
        owners.requireJavaKnowledgeSources(); var run=locked(id); if(!current(run,worker,attempt))return false;
        UUID project=(UUID)run.get("project_id"),actor=(UUID)run.get("created_by"); access.require(project,actor,"ADMIN");
        if(!config.hash().equals(run.get("configuration_hash")) || !config.indexVersion().equals(run.get("target_index_version")))throw new ApiProblem(409,"COMPUTE_CONFIG_CHANGED","索引配置与冻结任务不一致");
        SourceIndexWriter.requireDimensions(jdbc,config.dimensions());
        jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0))",Object.class,"source-index:"+project);
        var expected=manifest(run);
        if(!Json.canonical(sourceManifest(project)).equals(Json.canonical(expected)))throw new ApiProblem(409,"INDEX_INPUT_CHANGED","READY 资料范围发生变化，请重新发起索引重建");
        Map<UUID,Map<String,Object>> sources=new HashMap<>(); for(var source:expected)sources.put(UUID.fromString((String)source.get("id")),source);
        if(products.size()!=sources.size())throw new ApiProblem(409,"INDEX_STATE_INVALID","索引重建结果未覆盖全部冻结资料");
        int added=0,changed=0;
        for(var product:products) {
            var source=sources.remove(product.source()); if(source==null)throw new ApiProblem(409,"INDEX_STATE_INVALID","索引重建重复或超出资料范围");
            if(source.get("normalized_text_hash")!=null && !source.get("normalized_text_hash").equals(product.normalizedHash()))throw new ApiProblem(409,"SOURCE_HASH_MISMATCH","索引原文与已登记摘要不一致");
            int count=indexes.append(product.source(),config.indexVersion(),product.chunks(),true); added+=count; if(count>0)changed++;
        }
        var target=indexes.register(project,actor,config,true,id.toString());
        jdbc.update("UPDATE retrieval_index_build_runs SET status='SUCCEEDED',finished_at=clock_timestamp(),source_count=?,reindexed_source_count=?,reindexed_chunk_count=?,error_code=NULL,error_message=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id=?",products.size(),changed,added,id);
        audit.append(project,actor,"ProjectRetrievalIndex",(UUID)target.get("id"),"PROJECT_RETRIEVAL_INDEX_REBUILT",id.toString(),
            Map.of("indexVersion",config.indexVersion(),"sourceCount",products.size(),"reindexedSourceCount",changed,"reindexedChunkCount",added),null,null); return true;
    }
    @Transactional public void failure(UUID id,String worker,int attempt,ApiProblem error) {
        if(!owners.knowledgeSourcesAreJava())return; owners.requireJavaKnowledgeSources(); var run=locked(id); if(!current(run,worker,attempt))return;
        boolean retry=Set.of("COMPUTE_BUSY","COMPUTE_UNAVAILABLE","MODEL_UNAVAILABLE","COMPUTE_TIMEOUT","DATABASE_UNAVAILABLE").contains(error.code) && attempt<((Number)run.get("max_attempts")).intValue();
        if(retry)jdbc.update("UPDATE retrieval_index_build_runs SET available_at=clock_timestamp()+make_interval(secs=>?),lease_owner=NULL,lease_expires_at=NULL,last_error_code=?,error_code=?,error_message=? WHERE id=?",attempt==1?30:attempt==2?120:300,error.code,error.code,trim(error.getMessage()),id);
        else jdbc.update("UPDATE retrieval_index_build_runs SET status='FAILED',finished_at=clock_timestamp(),error_code=?,error_message=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=?",error.code,trim(error.getMessage()),id);
    }
    static List<Map<String,Object>> manifest(Map<String,Object> run) {
        Object value=Json.read(run.get("input_manifest").toString()); if(!(value instanceof List<?>))throw new ApiProblem(409,"INDEX_STATE_INVALID","重建任务没有有效的冻结资料范围");
        @SuppressWarnings("unchecked") var rows=(List<Map<String,Object>>)value; return rows;
    }
    private List<Map<String,Object>> sourceManifest(UUID project) {
        return jdbc.queryForList("SELECT id,content_hash,artifact_uri,extracted_artifact_uri,normalized_text_hash FROM source_revisions WHERE project_id=? AND processing_status='READY' ORDER BY id FOR SHARE",project)
            .stream().map(row->{ var copy=new LinkedHashMap<>(row); copy.put("id",row.get("id").toString()); return (Map<String,Object>)copy; }).toList();
    }
    private Map<String,Object> locked(UUID id) {
        var refs=jdbc.queryForList("SELECT project_id FROM retrieval_index_build_runs WHERE id=?",id); if(refs.isEmpty())return null;
        jdbc.queryForList("SELECT id FROM projects WHERE id=? FOR SHARE",refs.getFirst().get("project_id"));
        var rows=jdbc.queryForList("SELECT *,clock_timestamp() AS database_now FROM retrieval_index_build_runs WHERE id=? FOR UPDATE",id); return rows.isEmpty()?null:rows.getFirst();
    }
    private boolean current(Map<String,Object> run,String worker,int attempt) {
        return run!=null && "RUNNING".equals(run.get("status")) && worker.equals(run.get("lease_owner")) && ((Number)run.get("attempt_no")).intValue()==attempt
            && run.get("lease_expires_at") instanceof Timestamp end && end.after((Timestamp)run.get("database_now"));
    }
    private static String trim(String text) { return text.substring(0,text.offsetByCodePoints(0,Math.min(500,text.codePointCount(0,text.length())))); }
}
