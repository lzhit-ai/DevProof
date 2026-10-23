package ai.devproof.source;

import ai.devproof.infrastructure.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Short queue transactions and a separate network lane; no business transaction spans HTTP. */
@Component
public class GitHubSyncRuntime {
    private static final org.slf4j.Logger LOG=org.slf4j.LoggerFactory.getLogger(GitHubSyncRuntime.class);
    private final GitHubSyncStore store;
    private final GitHubSourceClient client;
    private final String worker;
    private final int lease;
    private final int maxPages;
    private final AtomicBoolean busy=new AtomicBoolean();
    private volatile Thread active;
    public GitHubSyncRuntime(GitHubSyncStore store,GitHubSourceClient client,@Value("${JAVA_SOURCE_WORKER_ID:}") String worker,@Value("${JOB_LEASE_SECONDS:60}") int lease,@Value("${GITHUB_SYNC_MAX_PAGES:5}") int maxPages) {
        if(lease<15 || lease>300 || maxPages<1 || maxPages>50)throw new IllegalArgumentException("Invalid source bounds"); this.store=store; this.client=client; this.worker=worker.isBlank()?"java-source-"+UUID.randomUUID():worker; this.lease=lease; this.maxPages=maxPages;
    }
    @Scheduled(fixedDelayString="${devproof.source-sync-poll-ms:2000}",initialDelayString="${devproof.source-sync-poll-ms:2000}")
    public void tick() {
        if(!busy.compareAndSet(false,true))return;
        try {
            Map<String,Object> run=store.claim(worker,lease); if(run==null) { busy.set(false); return; }
            active=Thread.startVirtualThread(()->execute(run));
        } catch(DataAccessException e) { busy.set(false); LOG.warn("source_sync_queue_unavailable"); }
        catch(RuntimeException e) { busy.set(false); LOG.warn("source_sync_claim_failed type={}",e.getClass().getSimpleName()); }
    }
    private void execute(Map<String,Object> run) {
        UUID id=(UUID)run.get("id"); int attempt=((Number)run.get("attempt_no")).intValue(); AtomicBoolean alive=new AtomicBoolean(true);
        ScheduledExecutorService heartbeat=Executors.newSingleThreadScheduledExecutor(Thread.ofVirtual().factory());
        int interval=Math.max(5,Math.min(15,lease/3));
        heartbeat.scheduleWithFixedDelay(()-> {
            try { if(!store.heartbeat(id,worker,attempt,lease))alive.set(false); }
            catch(DataAccessException e) { alive.set(false); LOG.warn("source_sync_heartbeat_unavailable run_id={}",id); }
            catch(RuntimeException e) { alive.set(false); }
        },interval,interval,TimeUnit.SECONDS);
        try {
            String slug=(String)run.get("repository_slug");
            Map<String,Object> cursor=Json.object(run.get("continuation_cursor").toString());
            int pages=((Number)run.get("page_count")).intValue();
            if(!GitHubSourceClient.resumable(cursor) && pages==0)cursor=GitHubSourceClient.initialCursor(slug);
            if(cursor.isEmpty() && pages>0) { store.complete(id,worker,attempt,false); return; }
            while(alive.get() && pages<maxPages) {
                GitHubSourceClient.Batch batch=client.fetchPage(slug,(String)run.get("api_base_url"),(String)run.get("secret_ref"),cursor,alive::get);
                if(!alive.get() || !store.checkpoint(id,worker,attempt,batch.payload()))return;
                pages++; cursor=batch.payload().cursor();
                if(cursor.isEmpty()) { store.complete(id,worker,attempt,false); return; }
                if(batch.retryAt()!=null)throw new GitHubSourceClient.RateLimited(batch.retryAt());
            }
            if(alive.get())store.complete(id,worker,attempt,true);
        } catch(ApiProblem e) { failed(id,attempt,e); }
        catch(TransientDataAccessException e) { failed(id,attempt,new ApiProblem(503,"SOURCE_STORAGE_UNAVAILABLE","来源同步存储暂时不可用")); }
        catch(RuntimeException e) { LOG.warn("source_sync_failed run_id={} type={}",id,e.getClass().getSimpleName()); failed(id,attempt,new ApiProblem(503,"SOURCE_STORAGE_FAILED","来源同步未能完成，请检查服务端配置与实际响应")); }
        finally { alive.set(false); heartbeat.shutdownNow(); busy.set(false); }
    }
    private void failed(UUID id,int attempt,ApiProblem error) {
        try { store.failure(id,worker,attempt,error); }
        catch(RuntimeException e) { LOG.warn("source_sync_failure_not_persisted run_id={} code={}",id,error.code); }
    }
    @jakarta.annotation.PreDestroy public void close() { Thread task=active; if(task!=null)task.interrupt(); }
}
