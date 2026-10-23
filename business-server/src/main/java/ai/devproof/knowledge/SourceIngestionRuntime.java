package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SourceIngestionRuntime {
    private static final org.slf4j.Logger LOG=org.slf4j.LoggerFactory.getLogger(SourceIngestionRuntime.class);
    private final SourceIngestionStore store;
    private final ComputeClient compute;
    private final ControlledArtifacts artifacts;
    private final ComputeExecutionLane lane;
    private final String worker="java-ingestion-"+UUID.randomUUID();
    private final int lease,sourceMax;
    private final AtomicBoolean busy=new AtomicBoolean();
    private volatile Thread active;
    public SourceIngestionRuntime(SourceIngestionStore store,ComputeClient compute,ControlledArtifacts artifacts,ComputeExecutionLane lane,
        @Value("${JOB_LEASE_SECONDS:60}") int lease,@Value("${SOURCE_MAX_BYTES:104857600}") int sourceMax) {
        if(lease<15 || lease>300)throw new IllegalArgumentException("Invalid ingestion lease");
        this.store=store; this.compute=compute; this.artifacts=artifacts; this.lane=lane; this.lease=lease; this.sourceMax=sourceMax;
    }
    @Scheduled(fixedDelayString="${devproof.ingestion-poll-ms:2000}",initialDelayString="${devproof.ingestion-poll-ms:2000}")
    public void tick() {
        if(!busy.compareAndSet(false,true))return;
        if(!lane.acquire()) { busy.set(false); return; }
        try {
            store.expireOne(); var job=store.claim(worker,lease); if(job==null) { lane.release(); busy.set(false); return; }
            active=Thread.startVirtualThread(()->execute(job));
        } catch(RuntimeException e) { lane.release(); busy.set(false); LOG.warn("source_ingestion_claim_failed type={}",e.getClass().getSimpleName()); }
    }
    private void execute(Map<String,Object> claimed) {
        UUID id=(UUID)claimed.get("id"); int attempt=((Number)claimed.get("attempt_no")).intValue();
        var alive=new AtomicBoolean(true); Thread execution=Thread.currentThread();
        var heartbeat=Executors.newSingleThreadScheduledExecutor(Thread.ofVirtual().factory());
        int interval=Math.max(5,Math.min(15,lease/3));
        heartbeat.scheduleWithFixedDelay(()-> {
            try { if(!store.heartbeat(id,worker,attempt,lease)) { alive.set(false); execution.interrupt(); } }
            catch(RuntimeException e) { alive.set(false); execution.interrupt(); }
        },interval,interval,TimeUnit.SECONDS);
        try {
            var job=store.prepare(id,worker,attempt,null); if(job==null)return;
            ComputeClient.Configuration configuration;
            if(job.get("configuration_hash")==null) {
                configuration=compute.configuration(); job=store.prepare(id,worker,attempt,configuration); if(job==null)return;
            } else configuration=ComputeClient.frozen(job.get("compute_configuration").toString(),(String)job.get("configuration_hash"));
            byte[] bytes=artifacts.read((String)job.get("artifact_uri"),sourceMax,(String)job.get("content_hash"));
            var result=compute.extract(bytes,(String)job.get("original_filename"),Boolean.TRUE.equals(job.get("force_ocr")),(String)job.get("media_type"),configuration);
            if(alive.get())store.complete(id,worker,attempt,result,configuration);
        } catch(ApiProblem e) { failed(id,attempt,e); }
        catch(RuntimeException e) { LOG.warn("source_ingestion_failed job_id={} type={}",id,e.getClass().getSimpleName()); failed(id,attempt,new ApiProblem(503,"SOURCE_INGESTION_FAILED","资料解析或存储未能完成")); }
        finally { alive.set(false); heartbeat.shutdownNow(); lane.release(); busy.set(false); }
    }
    private void failed(UUID id,int attempt,ApiProblem error) {
        Thread.interrupted(); // Persist the actual stop reason before this virtual thread exits.
        try { store.failure(id,worker,attempt,error); } catch(RuntimeException e) { LOG.warn("source_ingestion_failure_not_persisted job_id={} code={}",id,error.code); }
    }
    @jakarta.annotation.PreDestroy public void close() { Thread current=active; if(current!=null)current.interrupt(); }
}
