package ai.devproof.report;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Short PostgreSQL transaction: claim, create draft, complete and emit fact. No external I/O. */
@Service
public class ReportDraftQueue {
    private static final org.slf4j.Logger LOG=org.slf4j.LoggerFactory.getLogger(ReportDraftQueue.class);
    private final JdbcTemplate jdbc;
    private final BusinessOwnership owners;
    private final ReportLifecycle reports;
    public ReportDraftQueue(JdbcTemplate jdbc,BusinessOwnership owners,ReportLifecycle reports) {
        this.jdbc=jdbc; this.owners=owners; this.reports=reports;
    }
    @Transactional
    public void next() {
        if(!owners.reportsAreJava())return;
        owners.requireJavaReports();
        var jobs=jdbc.queryForList("SELECT * FROM report_generation_jobs WHERE status='PENDING' AND available_at<=clock_timestamp() ORDER BY available_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1");
        if(jobs.isEmpty())return;
        Map<String,Object> job=jobs.getFirst(); UUID run=(UUID)job.get("run_id");
        int attempt=((Number)job.get("attempt_no")).intValue()+1;
        jdbc.update("UPDATE report_generation_jobs SET attempt_no=? WHERE run_id=?",attempt,run);
        UUID id;
        try { id=reports.createAutomatic(run); }
        catch(ApiProblem e) { failed(run,e.code); return; }
        catch(DataAccessException e) {
            if(attempt<3) {
                jdbc.update("UPDATE report_generation_jobs SET available_at=clock_timestamp()+make_interval(secs=>?),last_error_code='REPORT_STORAGE_ERROR' WHERE run_id=?",attempt*5,run);
                event(run,"QUEUED",Map.of("errorCode","REPORT_STORAGE_ERROR","automatic",true,"attempt",attempt));
            } else failed(run,"REPORT_STORAGE_ERROR");
            return;
        }
        catch(RuntimeException e) { failed(run,"REPORT_GENERATION_FAILED"); LOG.error("report_draft_generation_failed type={}",e.getClass().getSimpleName()); return; }
        jdbc.update("UPDATE report_generation_jobs SET status='SUCCEEDED',report_id=?,finished_at=clock_timestamp() WHERE run_id=?",id,run);
        event(run,"SUCCEEDED",Map.of("reportId",id.toString(),"automatic",true));
    }
    private void failed(UUID run,String code) {
        jdbc.update("UPDATE report_generation_jobs SET status='FAILED',last_error_code=?,finished_at=clock_timestamp() WHERE run_id=?",code,run);
        jdbc.update("UPDATE analysis_runs SET run_status='PARTIALLY_COMPLETED',updated_at=clock_timestamp() WHERE id=? AND run_status='SUCCEEDED'",run);
        jdbc.update("UPDATE analysis_run_manifests SET degradation=coalesce(degradation,'{}'::jsonb)||jsonb_build_object('reportDraft',jsonb_build_object('code',CAST(? AS text))) WHERE run_id=?",code,run);
        event(run,"FAILED",Map.of("errorCode",code,"automatic",true));
    }
    private void event(UUID run,String status,Map<String,Object> payload) {
        jdbc.update("INSERT INTO run_events(id,run_id,node_id,event_type,status,correlation_id,payload_redacted) VALUES(?,?,'report-draft','REPORT_DRAFT',?,?,CAST(? AS jsonb))",
            UUID.randomUUID(),run,status,run.toString(),Json.write(payload));
    }
    @Component
    public static class Scheduler {
        private static final org.slf4j.Logger LOG=org.slf4j.LoggerFactory.getLogger(Scheduler.class);
        private final ReportDraftQueue queue;
        public Scheduler(ReportDraftQueue queue) { this.queue=queue; }
        @Scheduled(fixedDelayString="${devproof.report-draft-poll-ms:2000}",initialDelayString="${devproof.report-draft-poll-ms:2000}")
        public void drain() {
            try { queue.next(); }
            catch(DataAccessException e) { LOG.warn("report_draft_queue_database_unavailable"); }
            catch(RuntimeException e) { LOG.error("report_draft_queue_failed type={}",e.getClass().getSimpleName()); }
        }
    }
}
