package ai.devproof.retrieval;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.verification.VerificationToolScope;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Authorization and ranked reads run in short transactions, on either side of external embedding I/O. */
@Service
public class SnapshotSearchStore {
    public record Scope(UUID snapshot,UUID project,String hash,List<UUID> sources,List<UUID> evidence,
                        String activeIndex,Map<UUID,Map<String,Object>> sourceRows,List<Map<String,Object>> evidenceRows) {}
    private record Identity(String source,int index) {}
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final VerificationToolScope tasks;
    private final PostgresHybridRetriever retriever;
    public SnapshotSearchStore(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,VerificationToolScope tasks,PostgresHybridRetriever retriever) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.tasks=tasks; this.retriever=retriever;
    }
    @Transactional public Scope load(UUID snapshot,UUID actor,Map<String,Object> taskPayload) {
        owners.requireJavaKnowledgeSources();
        var snapshots=jdbc.queryForList("SELECT s.snapshot_hash,t.project_id FROM input_snapshots s JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE s.id=?",snapshot);
        if(snapshots.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","输入快照不存在");
        UUID project=(UUID)snapshots.getFirst().get("project_id"); String hash=(String)snapshots.getFirst().get("snapshot_hash");
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        Set<String> allowed=null;
        if(taskPayload!=null) {
            tasks.revalidate(taskPayload); var run=tasks.require(taskPayload);
            if(!snapshot.equals(run.get("snapshot_id")) || !hash.equals(run.get("snapshot_hash")) || !actor.toString().equals(taskPayload.get("actorId")))
                throw new ApiProblem(409,"INPUT_STALE","检索范围与当前任务冻结输入不一致");
            if(!(taskPayload.get("allowedEvidenceIds") instanceof List<?> values))throw new ApiProblem(409,"INPUT_STALE","任务证据授权范围缺失");
            allowed=new HashSet<>(); for(Object value:values)allowed.add((String)value);
        }
        List<UUID> sourceIds=new ArrayList<>(); Map<UUID,Map<String,Object>> sources=new HashMap<>();
        for(var source:jdbc.queryForList("""
            SELECT s.*,b.content_hash AS frozen_hash,k.name AS knowledge_base_name FROM input_snapshot_sources b
            JOIN source_revisions s ON s.id=b.source_revision_id LEFT JOIN knowledge_bases k ON k.id=s.knowledge_base_id WHERE b.snapshot_id=?
            """,snapshot)) {
            if(!Objects.equals(source.get("frozen_hash"),source.get("content_hash")))throw new ApiProblem(409,"INPUT_STALE","快照绑定的资料版本摘要已改变");
            UUID id=(UUID)source.get("id"); sourceIds.add(id); sources.put(id,source);
        }
        List<Map<String,Object>> evidence=new ArrayList<>();
        for(var row:jdbc.queryForList("SELECT id,content_hash,excerpt_safe,locator_precision,locator::text AS locator_json FROM evidence_items WHERE snapshot_id=? AND project_id=? AND source_type='DOCUMENT'",snapshot,project))
            if(allowed==null || allowed.contains(row.get("id").toString()))evidence.add(row);
        var active=jdbc.queryForList("SELECT index_version FROM project_retrieval_indexes WHERE project_id=? AND status='ACTIVE'",project);
        return new Scope(snapshot,project,hash,List.copyOf(sourceIds),evidence.stream().map(row->(UUID)row.get("id")).toList(),
            active.isEmpty()?null:(String)active.getFirst().get("index_version"),sources,List.copyOf(evidence));
    }
    public record Result(List<Map<String,Object>> items,Map<String,Object> retrieval) {}
    @Transactional public Result search(Scope before,UUID actor,Map<String,Object> taskPayload,String query,int limit,List<String> preferred,
        List<Double> embedding,String index,String unavailableCode) {
        Scope scope=load(before.snapshot(),actor,taskPayload);
        if(!before.hash().equals(scope.hash()) || !new HashSet<>(before.sources()).equals(new HashSet<>(scope.sources())) || !new HashSet<>(before.evidence()).equals(new HashSet<>(scope.evidence())))
            throw new ApiProblem(409,"INPUT_STALE","查询期间冻结资料或证据范围发生变化");
        if(embedding!=null && !Objects.equals(before.activeIndex(),scope.activeIndex())) { embedding=null; unavailableCode="MODEL_INDEX_CHANGED"; }
        var candidates=retriever.search(scope.sources(),scope.evidence(),query,limit,embedding,embedding==null?null:index);
        Map<Identity,Map<String,Object>> byIdentity=new HashMap<>(); Map<String,Map<String,Object>> byChunk=new HashMap<>();
        for(var row:scope.evidenceRows()) {
            var locator=Json.object((String)row.get("locator_json"));
            if(locator.get("sourceRevisionId") instanceof String source && locator.get("chunkIndex") instanceof Number position)
                byIdentity.put(new Identity(source,position.intValue()),row);
            if(locator.get("chunkId") instanceof String chunk)byChunk.put(chunk,row);
        }
        Map<UUID,String> roles=new HashMap<>();
        for(var entry:scope.sourceRows().entrySet()) {
            var source=entry.getValue(); String role=(String)source.get("source_role");
            roles.put(entry.getKey(),"知识库".equals(UnicodeText.strip(role)) && source.get("knowledge_base_name") instanceof String name?name:role);
        }
        List<RetrievalRanking.Candidate> matched=new ArrayList<>(); Map<UUID,Map<String,Object>> match=new HashMap<>(); Map<UUID,RetrievalRanking.Quality> metadata=new HashMap<>();
        for(var candidate:candidates) {
            var item=byIdentity.get(new Identity(candidate.source().toString(),candidate.index()));
            if(item==null || !candidate.hash().equals(item.get("content_hash")))item=byChunk.get(candidate.chunk().toString());
            if(item==null || !candidate.hash().equals(item.get("content_hash")))continue;
            matched.add(candidate); match.put(candidate.chunk(),item); var source=scope.sourceRows().get(candidate.source());
            metadata.put(candidate.chunk(),new RetrievalRanking.Quality((String)item.get("locator_precision"),ocr(source)));
        }
        var signals=RetrievalRanking.rank(matched,roles,preferred,metadata); List<Map<String,Object>> items=new ArrayList<>();
        for(var candidate:matched) {
            var evidence=match.get(candidate.chunk()); var source=scope.sourceRows().get(candidate.source()); var signal=signals.get(candidate.chunk());
            Map<String,Object> raw=new LinkedHashMap<>();
            if(candidate.ftsRank()!=null) { raw.put("ftsRank",candidate.ftsRank()); raw.put("ftsScore",candidate.ftsScore()); }
            if(candidate.vectorRank()!=null) { raw.put("vectorRank",candidate.vectorRank()); raw.put("vectorScore",candidate.vectorScore()); }
            Map<String,Object> ranking=new LinkedHashMap<>(); ranking.put("rrfScore",RetrievalRanking.round(signal.rrf())); ranking.put("normalizedRrfScore",RetrievalRanking.round(signal.normalizedRrf()));
            ranking.put("sourceRole",source==null?null:source.get("source_role")); ranking.put("businessRole",roles.get(candidate.source()));
            ranking.put("sourceRoleMatch",RetrievalRanking.round(signal.role())); ranking.put("evidenceQuality",RetrievalRanking.round(signal.quality())); ranking.put("finalScore",RetrievalRanking.round(signal.score()));
            ranking.put("weights",Map.of("rrf",0.75,"sourceRole",0.15,"evidenceQuality",0.10));
            Map<String,Object> item=new LinkedHashMap<>(); item.put("evidenceId",evidence.get("id").toString()); item.put("excerpt",evidence.get("excerpt_safe"));
            item.put("locator",Json.object((String)evidence.get("locator_json"))); item.put("precision",evidence.get("locator_precision")); item.put("score",RetrievalRanking.round(signal.score()));
            item.put("retrieval",raw); item.put("ranking",ranking); item.put("whySelected",RetrievalRanking.reasons(candidate,roles.getOrDefault(candidate.source(),""),preferred,(String)evidence.get("locator_precision"),ocr(source))); items.add(item);
        }
        // Java's object-list sort is stable, matching Python's sort on the rounded public score.
        items.sort(Comparator.comparingDouble((Map<String,Object> item)->((Number)item.get("score")).doubleValue()).reversed());
        Map<String,Object> status=new LinkedHashMap<>(); status.put("mode",embedding==null?"LEXICAL":"HYBRID"); status.put("vectorStatus",embedding==null?"UNAVAILABLE":"AVAILABLE");
        status.put("indexVersion",embedding==null?null:index); status.put("errorCode",unavailableCode);
        return new Result(List.copyOf(items.subList(0,Math.min(items.size(),limit))),status);
    }
    private static Double ocr(Map<String,Object> source) { return source!=null && source.get("ocr_confidence") instanceof Number value?value.doubleValue():null; }
}
