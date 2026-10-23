package ai.devproof.retrieval;

import ai.devproof.infrastructure.*;
import ai.devproof.knowledge.ComputeClient;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class SnapshotSearchService {
    private final SnapshotSearchStore store;
    private final ComputeClient compute;
    private final EmbeddingProfile profile;
    public SnapshotSearchService(SnapshotSearchStore store,ComputeClient compute,EmbeddingProfile profile) { this.store=store; this.compute=compute; this.profile=profile; }
    public SnapshotSearchStore.Result search(UUID snapshot,UUID actor,String query,int limit,List<String> preferred,Map<String,Object> taskPayload) {
        var scope=store.load(snapshot,actor,taskPayload);
        if(scope.sources().isEmpty() || scope.evidence().isEmpty())return new SnapshotSearchStore.Result(List.of(),Map.of("mode","EMPTY","vectorStatus","NOT_REQUESTED"));
        Map<String,Object> embedding=profile.body();
        if(taskPayload!=null)embedding=frozenProfile(taskPayload);
        String index=EmbeddingProfile.indexVersion(embedding),error=null; List<Double> vector=null;
        try {
            if(scope.activeIndex()!=null && !scope.activeIndex().equals(index))throw new ApiProblem(409,"MODEL_INDEX_UNAVAILABLE","配置的查询模型与项目活动索引不一致");
            var actual=compute.configuration();
            if(!embedding.equals(actual.body().get("embedding")))throw new ApiProblem(409,"MODEL_CONFIG_CHANGED","计算服务查询模型与当前冻结配置不一致");
            if(!actual.embeddingConfigured())throw new ApiProblem(503,"MODEL_NOT_CONFIGURED","嵌入模型凭据未配置");
            vector=compute.embed(List.of(query),actual).getFirst();
        } catch(ApiProblem unavailable) {
            error=unavailable.code;
        }
        return store.search(scope,actor,taskPayload,query,limit,preferred,vector,index,error);
    }
    @SuppressWarnings("unchecked") private Map<String,Object> frozenProfile(Map<String,Object> payload) {
        var manifest=(Map<String,Object>)payload.get("agentManifest"); var configuration=(Map<String,Object>)manifest.get("executionConfiguration");
        if(!(configuration.get("documentEmbeddingConfiguration") instanceof Map<?,?> value))throw new ApiProblem(409,"INPUT_STALE","任务未冻结资料检索模型配置");
        return (Map<String,Object>)value;
    }
}
