package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SourceIngestionStore {
    private final JdbcTemplate jdbc;
    private final BusinessOwnership owners;
    private final ProjectAccess access;
    private final JavaArtifacts artifacts;
    private final BusinessAudit audit;
    private final SourceIndexWriter indexes;
    public SourceIngestionStore(JdbcTemplate jdbc,BusinessOwnership owners,ProjectAccess access,JavaArtifacts artifacts,BusinessAudit audit,SourceIndexWriter indexes) {
        this.jdbc=jdbc; this.owners=owners; this.access=access; this.artifacts=artifacts; this.audit=audit; this.indexes=indexes;
    }
    @Transactional public Map<String,Object> claim(String worker,int lease) {
        if(!owners.knowledgeSourcesAreJava())return null; owners.requireJavaKnowledgeSources();
        var rows=jdbc.queryForList("""
            SELECT j.*,s.project_id FROM source_ingestion_jobs j JOIN source_revisions s ON s.id=j.source_revision_id
            WHERE j.attempt_no<j.max_attempts AND (j.job_status='QUEUED' AND (j.available_at IS NULL OR j.available_at<=clock_timestamp())
                OR j.job_status='RUNNING' AND j.lease_expires_at<clock_timestamp())
            ORDER BY j.available_at NULLS FIRST,j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1
            """);
        if(rows.isEmpty())return null; var row=rows.getFirst(); int attempt=((Number)row.get("attempt_no")).intValue()+1;
        jdbc.update("UPDATE source_ingestion_jobs SET job_status='RUNNING',executor_owner='JAVA',attempt_no=?,lease_owner=?,lease_expires_at=clock_timestamp()+make_interval(secs=>?),heartbeat_at=clock_timestamp(),available_at=NULL,updated_at=clock_timestamp() WHERE id=?",attempt,worker,lease,row.get("id"));
        row.put("attempt_no",attempt); return row;
    }
    @Transactional public void expireOne() {
        if(!owners.knowledgeSourcesAreJava())return; owners.requireJavaKnowledgeSources();
        var rows=jdbc.queryForList("SELECT id FROM source_ingestion_jobs WHERE job_status='RUNNING' AND attempt_no>=max_attempts AND lease_expires_at<clock_timestamp() ORDER BY lease_expires_at LIMIT 1");
        if(rows.isEmpty())return; var job=locked((UUID)rows.getFirst().get("id")); if(job==null)return;
        if("RUNNING".equals(job.get("job_status")) && ((Number)job.get("attempt_no")).intValue()>=((Number)job.get("max_attempts")).intValue()
            && job.get("lease_expires_at") instanceof Timestamp end && end.before((Timestamp)job.get("database_now")))
            terminal(job,"MAX_ATTEMPTS_EXCEEDED","资料入库租约过期且尝试次数耗尽");
    }
    @Transactional public Map<String,Object> prepare(UUID id,String worker,int attempt,ComputeClient.Configuration bind) {
        owners.requireJavaKnowledgeSources(); var job=locked(id); if(!current(job,worker,attempt))return null;
        UUID project=(UUID)job.get("project_id"),actor=(UUID)job.get("requested_by");
        access.require(project,actor,"SUBMITTER","ADMIN");
        if("READY".equals(job.get("processing_status"))) {
            jdbc.update("UPDATE source_ingestion_jobs SET job_status='SUCCEEDED',lease_owner=NULL,lease_expires_at=NULL,updated_at=clock_timestamp() WHERE id=?",id); return null;
        }
        if(job.get("configuration_hash")==null) {
            if(bind==null)return job;
            jdbc.update("UPDATE source_ingestion_jobs SET compute_configuration=CAST(? AS jsonb),configuration_hash=? WHERE id=?",Json.canonical(bind.body()),bind.hash(),id);
            job.put("compute_configuration",Json.canonical(bind.body())); job.put("configuration_hash",bind.hash());
        }
        jdbc.update("UPDATE source_revisions SET processing_status='PARSING',failure_code=NULL,updated_at=clock_timestamp() WHERE id=?",job.get("source_revision_id"));
        return job;
    }
    @Transactional public boolean heartbeat(UUID id,String worker,int attempt,int lease) {
        if(!owners.knowledgeSourcesAreJava())return false; owners.requireJavaKnowledgeSources();
        return jdbc.update("UPDATE source_ingestion_jobs SET heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+make_interval(secs=>?) WHERE id=? AND job_status='RUNNING' AND lease_owner=? AND attempt_no=? AND lease_expires_at>clock_timestamp()",lease,id,worker,attempt)==1;
    }
    @Transactional public boolean complete(UUID id,String worker,int attempt,ComputeClient.Extraction result,ComputeClient.Configuration config) {
        owners.requireJavaKnowledgeSources(); var job=locked(id); if(!current(job,worker,attempt))return false;
        UUID project=(UUID)job.get("project_id"),source=(UUID)job.get("source_revision_id"),actor=(UUID)job.get("requested_by");
        access.require(project,actor,"SUBMITTER","ADMIN");
        if(!result.contentHash().equals(job.get("content_hash")) || !result.configurationHash().equals(job.get("configuration_hash"))
            || !config.hash().equals(job.get("configuration_hash")))throw new ApiProblem(409,"SOURCE_HASH_MISMATCH","资料计算结果不属于当前冻结任务");
        SourceIndexWriter.requireDimensions(jdbc,config.dimensions());
        // Serialize index activation with other source/index completion on this project.
        jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(?,0))",Object.class,"source-index:"+project);
        var artifact=artifacts.save(project,"SOURCE_TEXT","source-text-v1","text/plain",result.normalizedText().getBytes(StandardCharsets.UTF_8));
        indexes.append(source,result.indexVersion(),result.chunks(),"AVAILABLE".equals(result.indexingStatus()));
        if("AVAILABLE".equals(result.indexingStatus()))indexes.register(project,actor,config,false,id.toString());
        jdbc.update("""
            UPDATE source_revisions SET extracted_artifact_uri=?,normalized_text_hash=?,extraction_metadata=CAST(? AS jsonb),ocr_confidence=NULL,
                parser_version=?,processing_status='READY',failure_code=NULL,updated_at=clock_timestamp() WHERE id=?
            """,artifact.get("storage_uri"),result.normalizedTextHash(),Json.canonical(result.metadata()),result.parserVersion(),source);
        jdbc.update("UPDATE source_ingestion_jobs SET job_status='SUCCEEDED',lease_owner=NULL,lease_expires_at=NULL,last_error_code=NULL,last_error_message=NULL,updated_at=clock_timestamp() WHERE id=?",id);
        var facts=new LinkedHashMap<String,Object>(); facts.put("contentHash",result.contentHash()); facts.put("parserVersion",result.parserVersion()); facts.put("ocrConfidence",null);
        audit.append(project,actor,"SourceRevision",source,"SOURCE_REVISION_READY",id.toString(),facts,null,null); return true;
    }
    @Transactional public void failure(UUID id,String worker,int attempt,ApiProblem error) {
        if(!owners.knowledgeSourcesAreJava())return; owners.requireJavaKnowledgeSources(); var job=locked(id); if(!current(job,worker,attempt))return;
        if(attempt>=((Number)job.get("max_attempts")).intValue() || Set.of("COMPUTE_CONFIG_CHANGED","AUTH_FORBIDDEN","SOURCE_HASH_MISMATCH","MODEL_SCHEMA_INVALID").contains(error.code)) { terminal(job,error.code,error.getMessage()); return; }
        int delay=attempt==1?30:attempt==2?120:300;
        jdbc.update("UPDATE source_ingestion_jobs SET job_status='QUEUED',lease_owner=NULL,lease_expires_at=NULL,available_at=clock_timestamp()+make_interval(secs=>?),last_error_code=?,last_error_message=?,updated_at=clock_timestamp() WHERE id=?",delay,error.code,error.getMessage(),id);
        jdbc.update("UPDATE source_revisions SET failure_code=?,processing_status='PARSING',updated_at=clock_timestamp() WHERE id=? AND processing_status<>'READY'",error.code,job.get("source_revision_id"));
    }
    private Map<String,Object> locked(UUID id) {
        var refs=jdbc.queryForList("SELECT j.source_revision_id,s.project_id FROM source_ingestion_jobs j JOIN source_revisions s ON s.id=j.source_revision_id WHERE j.id=?",id); if(refs.isEmpty())return null;
        var ref=refs.getFirst(); jdbc.queryForList("SELECT id FROM projects WHERE id=? FOR SHARE",ref.get("project_id"));
        var sources=jdbc.queryForList("SELECT * FROM source_revisions WHERE id=? FOR UPDATE",ref.get("source_revision_id")); if(sources.isEmpty())return null;
        var jobs=jdbc.queryForList("SELECT *,clock_timestamp() AS database_now FROM source_ingestion_jobs WHERE id=? FOR UPDATE",id); if(jobs.isEmpty())return null;
        var result=jobs.getFirst(); result.putAll(sources.getFirst()); result.put("source_revision_id",ref.get("source_revision_id")); result.put("id",id); return result;
    }
    private boolean current(Map<String,Object> job,String worker,int attempt) {
        return job!=null && "RUNNING".equals(job.get("job_status")) && worker.equals(job.get("lease_owner")) && ((Number)job.get("attempt_no")).intValue()==attempt
            && job.get("lease_expires_at") instanceof Timestamp end && end.after((Timestamp)job.get("database_now"));
    }
    private void terminal(Map<String,Object> job,String code,String message) {
        jdbc.update("UPDATE source_ingestion_jobs SET job_status='FAILED',lease_owner=NULL,lease_expires_at=NULL,last_error_code=?,last_error_message=?,updated_at=clock_timestamp() WHERE id=?",code,message,job.get("id"));
        jdbc.update("UPDATE source_revisions SET processing_status='FAILED',failure_code=?,updated_at=clock_timestamp() WHERE id=? AND processing_status<>'READY'",code,job.get("source_revision_id"));
    }
}
