package ai.devproof.source;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GitHubSyncStore {
    private final JdbcTemplate jdbc;
    private final BusinessOwnership owners;
    private final ProjectAccess access;
    private final BusinessAudit audit;
    private final GitHubResourceWriter resources;
    public GitHubSyncStore(JdbcTemplate jdbc,BusinessOwnership owners,ProjectAccess access,BusinessAudit audit,GitHubResourceWriter resources) {
        this.jdbc=jdbc; this.owners=owners; this.access=access; this.audit=audit; this.resources=resources;
    }
    @Transactional public Map<String,Object> claim(String worker,int lease) {
        if(!owners.githubSourcesAreJava())return null; owners.requireJavaGitHubSources();
        jdbc.update("WITH expired AS (SELECT id FROM source_sync_runs WHERE status='RUNNING' AND attempt_no>=max_attempts AND lease_expires_at<clock_timestamp() FOR UPDATE SKIP LOCKED) UPDATE source_sync_runs SET status='FAILED',error_code='MAX_ATTEMPTS_EXCEEDED',error_message='来源同步租约过期且尝试次数已耗尽',last_error_code='MAX_ATTEMPTS_EXCEEDED',finished_at=clock_timestamp(),lease_owner=NULL,lease_expires_at=NULL WHERE id IN (SELECT id FROM expired)");
        var rows=jdbc.queryForList("""
            SELECT r.*,c.project_id,c.repository_slug,c.api_base_url,c.secret_ref,c.is_active
            FROM source_sync_runs r JOIN external_connections c ON c.id=r.connection_id
            WHERE r.status='RUNNING' AND r.attempt_no<r.max_attempts AND (r.available_at IS NULL OR r.available_at<=clock_timestamp())
              AND (r.lease_owner IS NULL OR r.lease_expires_at IS NULL OR r.lease_expires_at<clock_timestamp())
            ORDER BY r.started_at,r.id FOR UPDATE OF r SKIP LOCKED LIMIT 1
            """);
        if(rows.isEmpty())return null; Map<String,Object> run=rows.getFirst();
        if(run.get("requested_by")==null) { terminal(run,"REQUESTER_MISSING","旧同步请求未记录实际发起人"); return null; }
        try { access.require((UUID)run.get("project_id"),(UUID)run.get("requested_by"),"SUBMITTER","ADMIN"); }
        catch(ApiProblem e) { terminal(run,"AUTH_REVOKED","同步发起者授权已失效"); return null; }
        if(!Boolean.TRUE.equals(run.get("is_active"))) { terminal(run,"RESOURCE_NOT_FOUND","外部来源连接已停用"); return null; }
        int attempt=((Number)run.get("attempt_no")).intValue()+1;
        jdbc.update("UPDATE source_sync_runs SET executor_owner='JAVA',lease_owner=?,lease_expires_at=clock_timestamp()+make_interval(secs=>?),heartbeat_at=clock_timestamp(),available_at=NULL,attempt_no=?,error_code=NULL,error_message=NULL WHERE id=?",worker,lease,attempt,run.get("id"));
        run.put("attempt_no",attempt); run.put("lease_owner",worker); return run;
    }
    @Transactional public boolean heartbeat(UUID id,String worker,int attempt,int lease) {
        if(!owners.githubSourcesAreJava())return false; owners.requireJavaGitHubSources();
        return jdbc.update("UPDATE source_sync_runs SET heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+make_interval(secs=>?) WHERE id=? AND status='RUNNING' AND lease_owner=? AND attempt_no=? AND lease_expires_at>clock_timestamp()",lease,id,worker,attempt)==1;
    }
    @Transactional public boolean checkpoint(UUID id,String worker,int attempt,GitHubSourceClient.Payload payload) {
        owners.requireJavaGitHubSources(); Map<String,Object> run=current(id,worker,attempt); if(run==null)return false;
        Map<String,Object> connection=connection(run); if(connection==null)return false;
        GitHubResourceWriter.Counts counts=resources.persist(connection,(UUID)run.get("requested_by"),payload);
        // Data and the NEXT page advance in the same transaction, fenced by the lease.
        jdbc.update("UPDATE source_sync_runs SET fetched_count=fetched_count+?,changed_count=changed_count+?,page_count=page_count+?,continuation_cursor=CAST(? AS jsonb),error_code=NULL,error_message=NULL WHERE id=?",counts.fetched(),counts.changed(),payload.pageCount(),Json.write(payload.cursor()),id);
        return true;
    }
    @Transactional public boolean complete(UUID id,String worker,int attempt,boolean partial) {
        owners.requireJavaGitHubSources(); Map<String,Object> run=current(id,worker,attempt); if(run==null)return false;
        Map<String,Object> connection=connection(run); if(connection==null)return false;
        String status=partial?"PARTIALLY_SUCCEEDED":"SUCCEEDED";
        jdbc.update("UPDATE source_sync_runs SET status=?,finished_at=clock_timestamp(),available_at=NULL,lease_owner=NULL,lease_expires_at=NULL,error_code=NULL,error_message=NULL WHERE id=?",status,id);
        audit.append((UUID)connection.get("project_id"),(UUID)run.get("requested_by"),"SourceSyncRun",id,"SOURCE_SYNC_COMPLETED",id.toString(),Map.of("connectionId",connection.get("id").toString(),"status",status,"fetchedCount",run.get("fetched_count"),"changedCount",run.get("changed_count")),null,null); return true;
    }
    private Map<String,Object> connection(Map<String,Object> run) {
        var rows=jdbc.queryForList("SELECT * FROM external_connections WHERE id=? FOR UPDATE",run.get("connection_id"));
        if(rows.isEmpty() || !Boolean.TRUE.equals(rows.getFirst().get("is_active"))) { terminal(run,"RESOURCE_NOT_FOUND","来源连接已停用"); return null; }
        Map<String,Object> connection=rows.getFirst();
        try { access.require((UUID)connection.get("project_id"),(UUID)run.get("requested_by"),"SUBMITTER","ADMIN"); }
        catch(ApiProblem e) { terminal(run,"AUTH_REVOKED","同步发起者授权已失效"); return null; }
        return connection;
    }
    @Transactional public void failure(UUID id,String worker,int attempt,ApiProblem error) {
        if(!owners.githubSourcesAreJava())return; owners.requireJavaGitHubSources(); Map<String,Object> run=current(id,worker,attempt); if(run==null)return;
        if(error instanceof GitHubSourceClient.RateLimited limited) {
            if(!limited.quotaReset && attempt>=((Number)run.get("max_attempts")).intValue()) { terminal(run,error.code,error.getMessage()); return; }
            Instant retry=limited.retryAt;
            if(!limited.quotaReset) { Instant backoff=Instant.now().plusSeconds(60L << Math.min(attempt-1,5)); if(backoff.isAfter(retry))retry=backoff; }
            int attempts=limited.quotaReset?Math.max(((Number)run.get("max_attempts")).intValue(),attempt+1):((Number)run.get("max_attempts")).intValue();
            jdbc.update("UPDATE source_sync_runs SET available_at=?,lease_owner=NULL,lease_expires_at=NULL,last_error_code=?,last_error_message=?,error_code=?,error_message=?,max_attempts=? WHERE id=?",Timestamp.from(retry),error.code,error.getMessage(),error.code,error.getMessage(),attempts,id);
            return;
        }
        boolean retry=Set.of("SOURCE_UNAVAILABLE","SOURCE_STORAGE_UNAVAILABLE").contains(error.code) && attempt<((Number)run.get("max_attempts")).intValue();
        if(!retry) { terminal(run,error.code,error.getMessage()); return; }
        int delay=attempt==1?30:attempt==2?120:300;
        jdbc.update("UPDATE source_sync_runs SET available_at=clock_timestamp()+make_interval(secs=>?),lease_owner=NULL,lease_expires_at=NULL,last_error_code=?,last_error_message=?,error_code=?,error_message=? WHERE id=?",delay,error.code,error.getMessage(),error.code,error.getMessage(),id);
    }
    private Map<String,Object> current(UUID id,String worker,int attempt) {
        var rows=jdbc.queryForList("SELECT *,clock_timestamp() AS database_now FROM source_sync_runs WHERE id=? FOR UPDATE",id); if(rows.isEmpty())return null;
        Map<String,Object> row=rows.getFirst();
        return "RUNNING".equals(row.get("status")) && worker.equals(row.get("lease_owner")) && ((Number)row.get("attempt_no")).intValue()==attempt
            && row.get("lease_expires_at") instanceof Timestamp end && end.after((Timestamp)row.get("database_now"))?row:null;
    }
    private void terminal(Map<String,Object> run,String code,String message) {
        jdbc.update("UPDATE source_sync_runs SET status='FAILED',error_code=?,error_message=?,last_error_code=?,last_error_message=?,finished_at=clock_timestamp(),available_at=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id=?",code,message,code,message,run.get("id"));
        if(run.get("requested_by")!=null) {
            UUID project=jdbc.queryForObject("SELECT project_id FROM external_connections WHERE id=?",UUID.class,run.get("connection_id"));
            audit.append(project,(UUID)run.get("requested_by"),"SourceSyncRun",(UUID)run.get("id"),"SOURCE_SYNC_FAILED",run.get("id").toString(),Map.of("errorCode",code,"pageCount",run.get("page_count")),null,null);
        }
    }
}
