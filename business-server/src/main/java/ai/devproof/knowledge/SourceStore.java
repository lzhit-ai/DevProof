package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Source commands/read authorization. Network computation never runs in these transactions. */
@Service
public class SourceStore {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final JavaArtifacts artifacts;
    private final int maxAttempts;
    public SourceStore(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit,
                       JavaArtifacts artifacts,@Value("${JOB_MAX_ATTEMPTS:3}") int maxAttempts) {
        if(maxAttempts<1 || maxAttempts>10)throw new IllegalArgumentException("Invalid ingestion attempts");
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit; this.artifacts=artifacts; this.maxAttempts=maxAttempts;
    }
    @Transactional public void authorizeUpload(UUID project,UUID actor,UUID base) {
        owners.requireJavaKnowledgeSources(); access.require(project,actor,"SUBMITTER","ADMIN"); requireBase(project,base);
    }
    @Transactional public CommandStore.Result preflight(UUID project,UUID actor,UUID base,CommandStore.Context command) {
        owners.requireJavaKnowledgeSources(); access.require(project,actor,"SUBMITTER","ADMIN"); requireBase(project,base);
        try { return commands.replay(command); }
        catch(ApiProblem error) {
            if(!"IDEMPOTENCY_CONFLICT".equals(error.code))throw error;
            // Earlier uploads hashed the entire multipart wire body. Verify all actual source fields before replay;
            // historical request hashes/response bytes stay untouched.
            var rows=jdbc.queryForList("SELECT response_body::text AS body,response_status FROM idempotency_records WHERE principal_hash=? AND request_method=? AND request_path=? AND idempotency_key=? AND state='COMPLETED' AND response_status=201",
                Json.hash(command.authorization()),command.method(),command.path(),command.key());
            if(rows.isEmpty())throw error; var response=Json.object((String)rows.getFirst().get("body"));
            UUID source;
            try { source=UUID.fromString((String)response.get("id")); } catch(RuntimeException invalid) { throw error; }
            var originals=jdbc.queryForList("SELECT * FROM source_revisions WHERE id=? AND project_id=?",source,project);
            if(originals.isEmpty())throw error; var row=originals.getFirst();
            Map<String,Object> original=new LinkedHashMap<>(); original.put("sourceRole",row.get("source_role")); original.put("logicalName",row.get("logical_name"));
            original.put("filename",row.get("original_filename")); original.put("knowledgeBaseId",row.get("knowledge_base_id"));
            original.put("forceOcr",row.get("force_ocr")); original.put("contentHash",row.get("content_hash"));
            if(!Json.canonical(original).equals(Json.canonical(ApiInput.object(command.rawBody()))))throw error;
            return new CommandStore.Result(201,response);
        }
    }
    @Transactional public CommandStore.Result upload(UUID project,UUID actor,UUID base,String role,String name,String filename,
            boolean forceOcr,byte[] bytes,CommandStore.Context command,ComputeClient.Inspection inspection,ComputeClient.Configuration configuration) {
        owners.requireJavaKnowledgeSources(); lockProject(project); access.require(project,actor,"SUBMITTER","ADMIN"); requireBase(project,base);
        return commands.execute(command,201,()-> {
            if(!Json.hash(bytes).equals(inspection.contentHash()))throw new ApiProblem(409,"SOURCE_HASH_MISMATCH","资料与签名检查内容不一致");
            SourceIndexWriter.requireDimensions(jdbc,configuration.dimensions());
            UUID id=UUID.randomUUID(),job=UUID.randomUUID();
            int revision=jdbc.queryForObject("SELECT coalesce(max(revision_no),0)+1 FROM source_revisions WHERE project_id=? AND logical_name=?",Integer.class,project,name);
            var artifact=artifacts.save(project,"SOURCE_BINARY","source-binary-v1",inspection.mediaType(),bytes);
            jdbc.update("""
                INSERT INTO source_revisions(id,project_id,source_role,logical_name,revision_no,content_hash,artifact_uri,
                    original_filename,media_type,processing_status,extraction_metadata,knowledge_base_id,force_ocr)
                VALUES(?,?,?,?,?,?,?,?,?,'UPLOADED','{}'::jsonb,?,?)
                """,id,project,role,name,revision,inspection.contentHash(),artifact.get("storage_uri"),filename,inspection.mediaType(),base,forceOcr);
            jdbc.update("""
                INSERT INTO source_ingestion_jobs(id,source_revision_id,requested_by,job_status,attempt_no,max_attempts,executor_owner,compute_configuration,configuration_hash)
                VALUES(?,?,?,'QUEUED',0,?,'JAVA',CAST(? AS jsonb),?)
                """,job,id,actor,maxAttempts,Json.canonical(configuration.body()),configuration.hash());
            audit.append(project,actor,"SourceRevision",id,"SOURCE_INGESTION_QUEUED",command.correlationId(),
                Map.of("contentHash",inspection.contentHash(),"revisionNo",revision,"mediaType",inspection.mediaType()),null,null);
            var response=KnowledgeViews.fields(jdbc.queryForMap("SELECT * FROM source_revisions WHERE id=?",id),"id","project_id","logical_name","revision_no","content_hash","processing_status","parser_version","knowledge_base_id","force_ocr");
            response.put("ingestion_job_id",job); return response;
        });
    }
    @Transactional public List<Map<String,Object>> list(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        return jdbc.queryForList("""
            SELECT s.*,j.job_status AS ingestion_job_status,EXISTS(SELECT 1 FROM input_snapshot_sources b WHERE b.source_revision_id=s.id) AS in_snapshot
            FROM source_revisions s LEFT JOIN source_ingestion_jobs j ON j.source_revision_id=s.id
            WHERE (EXISTS(SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=?) AND EXISTS(
                SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=? AND b.knowledge_base_id=s.knowledge_base_id))
              OR (NOT EXISTS(SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=?) AND s.project_id=?)
            ORDER BY s.created_at DESC,s.id
            """,project,project,project,project).stream().map(KnowledgeViews::source).toList();
    }
    @Transactional public Map<String,Object> readable(UUID project,UUID id,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        var rows=jdbc.queryForList("""
            SELECT s.* FROM source_revisions s WHERE s.id=? AND (s.project_id=? OR EXISTS(
                SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=? AND b.knowledge_base_id=s.knowledge_base_id)) FOR SHARE OF s
            """,id,project,project);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","资料版本不存在或未挂载到当前项目"); return rows.getFirst();
    }
    @Transactional public List<Map<String,Object>> chunks(UUID project,UUID id,UUID actor) {
        readable(project,id,actor);
        return jdbc.queryForList("SELECT * FROM document_chunks WHERE source_revision_id=? ORDER BY chunk_index,index_version,id",id).stream().map(row->{
            var result=KnowledgeViews.fields(row,"id","chunk_index","content","index_version"); result.put("locator",KnowledgeViews.object(row.get("locator"))); return result;
        }).toList();
    }
    @Transactional public void delete(UUID project,UUID id,UUID actor,String correlation) {
        owners.requireJavaKnowledgeSources(); lockProject(project); access.require(project,actor,"SUBMITTER","ADMIN");
        var rows=jdbc.queryForList("SELECT * FROM source_revisions WHERE id=? AND project_id=? FOR UPDATE",id,project);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","资料版本不存在");
        if(jdbc.queryForObject("SELECT count(*) FROM input_snapshot_sources WHERE source_revision_id=?",Integer.class,id)>0)
            throw new ApiProblem(409,"SOURCE_FROZEN_IN_SNAPSHOT","该资料已冻结到核验快照，无法删除");
        try { jdbc.update("DELETE FROM source_revisions WHERE id=?",id); }
        catch(DataIntegrityViolationException e) { throw new ApiProblem(409,"SOURCE_IN_USE","资料仍被交付或核验记录引用，无法删除"); }
        // Registered content-addressed files can be shared; deleting a row never removes their bytes.
        audit.append(project,actor,"SourceRevision",id,"SOURCE_REVISION_DELETED",correlation,Map.of("contentHash",rows.getFirst().get("content_hash")),null,null);
    }
    private void requireBase(UUID project,UUID base) {
        if(base==null)return;
        var rows=jdbc.queryForList("SELECT project_id FROM knowledge_bases WHERE id=? FOR SHARE",base);
        if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","知识库不存在");
        if(!project.equals(rows.getFirst().get("project_id")) && jdbc.queryForObject("SELECT count(*) FROM project_knowledge_bases WHERE project_id=? AND knowledge_base_id=?",Integer.class,project,base)==0)
            throw new ApiProblem(403,"AUTH_FORBIDDEN","当前项目未挂载该知识库");
    }
    private void lockProject(UUID project) {
        if(jdbc.queryForList("SELECT id FROM projects WHERE id=? AND deleted_at IS NULL FOR UPDATE",project).isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","项目不存在");
    }
}
