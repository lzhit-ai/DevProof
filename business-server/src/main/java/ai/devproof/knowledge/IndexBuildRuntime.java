package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class IndexBuildRuntime {
    private static final org.slf4j.Logger LOG=org.slf4j.LoggerFactory.getLogger(IndexBuildRuntime.class);
    private final IndexBuildStore store;
    private final ComputeClient compute;
    private final ControlledArtifacts artifacts;
    private final ComputeExecutionLane lane;
    private final String worker="java-index-"+UUID.randomUUID();
    private final int lease,textMax,timeout;
    private final AtomicBoolean busy=new AtomicBoolean();
    private volatile Thread active;
    public IndexBuildRuntime(IndexBuildStore store,ComputeClient compute,ControlledArtifacts artifacts,ComputeExecutionLane lane,
        @Value("${JOB_LEASE_SECONDS:60}") int lease,@Value("${COMPUTE_RESULT_MAX_BYTES:268435456}") int textMax,
        @Value("${INDEX_BUILD_TIMEOUT_SECONDS:7200}") int timeout) {
        if(lease<15 || lease>300 || timeout<60 || timeout>86400)throw new IllegalArgumentException("Invalid index execution budget");
        this.store=store; this.compute=compute; this.artifacts=artifacts; this.lane=lane; this.lease=lease; this.textMax=textMax; this.timeout=timeout;
    }
    @Scheduled(fixedDelayString="${devproof.index-build-poll-ms:2500}",initialDelayString="${devproof.index-build-poll-ms:2500}")
    public void tick() {
        if(!busy.compareAndSet(false,true))return;
        if(!lane.acquire()) { busy.set(false); return; }
        try { var run=store.claim(worker,lease); if(run==null) { lane.release(); busy.set(false); return; } active=Thread.startVirtualThread(()->execute(run)); }
        catch(RuntimeException e) { lane.release(); busy.set(false); LOG.warn("index_build_claim_failed type={}",e.getClass().getSimpleName()); }
    }
    private void execute(Map<String,Object> claimed) {
        UUID id=(UUID)claimed.get("id"); int attempt=((Number)claimed.get("attempt_no")).intValue();
        var alive=new AtomicBoolean(true); var timedOut=new AtomicBoolean(); Thread execution=Thread.currentThread();
        var timer=Executors.newSingleThreadScheduledExecutor(Thread.ofVirtual().factory());
        int interval=Math.max(5,Math.min(15,lease/3));
        timer.scheduleWithFixedDelay(()-> {
            try { if(!store.heartbeat(id,worker,attempt,lease)) { alive.set(false); execution.interrupt(); } }
            catch(RuntimeException e) { alive.set(false); execution.interrupt(); }
        },interval,interval,TimeUnit.SECONDS);
        timer.schedule(()-> { timedOut.set(true); execution.interrupt(); },timeout,TimeUnit.SECONDS);
        try {
            var run=store.prepare(id,worker,attempt); if(run==null)return;
            var config=ComputeClient.frozen(run.get("compute_configuration").toString(),(String)run.get("configuration_hash"));
            List<IndexBuildStore.Product> products=new ArrayList<>();
            for(var source:IndexBuildStore.manifest(run)) {
                if(!alive.get() || timedOut.get())throw new ApiProblem(409,"LEASE_EXPIRED","索引执行已失效或超时");
                UUID sourceId=UUID.fromString((String)source.get("id"));
                boolean extracted=source.get("extracted_artifact_uri")!=null;
                String normalized=artifacts.text((String)source.get(extracted?"extracted_artifact_uri":"artifact_uri"),textMax,
                    (String)source.get(extracted?"normalized_text_hash":"content_hash"));
                List<ComputeClient.Chunk> parsed=compute.rechunk(normalized,config);
                Map<Integer,Map<String,Object>> existing=new HashMap<>();
                for(var row:store.existing(id,worker,attempt,sourceId))existing.put(((Number)row.get("chunk_index")).intValue(),row);
                List<ComputeClient.Chunk> missing=new ArrayList<>();
                for(var chunk:parsed) {
                    var prior=existing.remove(chunk.index());
                    if(prior==null)missing.add(chunk);
                    else if(!chunk.hash().equals(prior.get("text_hash")) || !chunk.content().equals(prior.get("content"))
                        || !chunk.locator().equals(Json.object((String)prior.get("locator_json"))) || !Boolean.TRUE.equals(prior.get("has_embedding")))
                        throw new ApiProblem(409,"INDEX_STATE_INVALID","已有派生索引与规范化原文不一致");
                }
                if(!existing.isEmpty())throw new ApiProblem(409,"INDEX_STATE_INVALID","已有索引包含额外分块");
                Map<Integer,List<Double>> vectors=new HashMap<>();
                for(int offset=0;offset<missing.size();offset+=64) {
                    if(!alive.get() || timedOut.get())throw new ApiProblem(409,"LEASE_EXPIRED","索引执行已失效或超时");
                    var batch=missing.subList(offset,Math.min(missing.size(),offset+64));
                    var actual=compute.embed(batch.stream().map(ComputeClient.Chunk::content).toList(),config);
                    for(int i=0;i<batch.size();i++)vectors.put(batch.get(i).index(),actual.get(i));
                }
                var chunks=parsed.stream().map(chunk->new ComputeClient.Chunk(chunk.index(),chunk.content(),chunk.hash(),chunk.locator(),vectors.get(chunk.index()))).toList();
                products.add(new IndexBuildStore.Product(sourceId,Json.hash(normalized),chunks));
            }
            if(alive.get() && !timedOut.get())store.complete(id,worker,attempt,products,config);
        } catch(ApiProblem e) { failed(id,attempt,timedOut.get()?new ApiProblem(503,"INDEX_BUILD_TIMEOUT","索引重建超过配置的执行时间上限"):e); }
        catch(RuntimeException e) { LOG.warn("index_build_failed run_id={} type={}",id,e.getClass().getSimpleName()); failed(id,attempt,new ApiProblem(503,"INDEX_BUILD_FAILED","派生索引计算或存储未能完成")); }
        finally { alive.set(false); timer.shutdownNow(); lane.release(); busy.set(false); }
    }
    private void failed(UUID id,int attempt,ApiProblem error) {
        Thread.interrupted();
        try { store.failure(id,worker,attempt,error); } catch(RuntimeException e) { LOG.warn("index_build_failure_not_persisted run_id={} code={}",id,error.code); }
    }
    @jakarta.annotation.PreDestroy public void close() { Thread current=active; if(current!=null)current.interrupt(); }
}
