package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Appends derived chunks and switches an index only at the caller's atomic acceptance point. */
@Component
public class SourceIndexWriter {
    private final JdbcTemplate jdbc;
    private final BusinessAudit audit;
    public SourceIndexWriter(JdbcTemplate jdbc,BusinessAudit audit) { this.jdbc=jdbc; this.audit=audit; }
    public static void requireDimensions(JdbcTemplate jdbc,int dimensions) {
        Integer actual=jdbc.queryForObject("SELECT atttypmod FROM pg_attribute WHERE attrelid='document_chunks'::regclass AND attname='embedding' AND NOT attisdropped",Integer.class);
        if(actual==null || actual!=dimensions)throw new ApiProblem(409,"MODEL_SCHEMA_INVALID","实际 pgvector 列维度与计算配置不一致");
    }
    public int append(UUID source,String index,List<ComputeClient.Chunk> chunks,boolean requireVectors) {
        List<Object[]> rows=new ArrayList<>();
        var current=jdbc.queryForList("SELECT *,locator::text AS locator_json FROM document_chunks WHERE source_revision_id=? AND index_version=? ORDER BY chunk_index",source,index);
        Map<Integer,Map<String,Object>> prior=new HashMap<>();
        for(var row:current)prior.put(((Number)row.get("chunk_index")).intValue(),row);
        for(var chunk:chunks) {
            var existing=prior.remove(chunk.index());
            if(existing!=null) {
                if(!chunk.hash().equals(existing.get("text_hash")) || !chunk.content().equals(existing.get("content"))
                    || !chunk.locator().equals(Json.object((String)existing.get("locator_json")))
                    || requireVectors && existing.get("embedding")==null)
                    throw new ApiProblem(409,"INDEX_STATE_INVALID","已有派生分块与不可变资料内容不一致");
            } else {
                if(requireVectors && chunk.vector()==null)throw new ApiProblem(409,"INDEX_STATE_INVALID","派生索引缺少实际嵌入结果");
                rows.add(new Object[]{UUID.randomUUID(),source,chunk.index(),chunk.content(),chunk.hash(),Json.canonical(chunk.locator()),index,
                    chunk.vector()==null?null:Json.canonical(chunk.vector())});
            }
        }
        if(!prior.isEmpty())throw new ApiProblem(409,"INDEX_STATE_INVALID","已有索引的分块数量与当前解析结果不一致");
        if(!rows.isEmpty())jdbc.batchUpdate("INSERT INTO document_chunks(id,source_revision_id,chunk_index,content,text_hash,locator,index_version,embedding) VALUES(?,?,?,?,?,CAST(? AS jsonb),?,CAST(? AS vector))",rows);
        return rows.size();
    }
    public Map<String,Object> register(UUID project,UUID actor,ComputeClient.Configuration config,boolean activate,String correlation) {
        String index=config.indexVersion();
        var active=jdbc.queryForList("SELECT * FROM project_retrieval_indexes WHERE project_id=? AND status='ACTIVE' FOR UPDATE",project);
        if(!activate && !active.isEmpty()) {
            if(!index.equals(active.getFirst().get("index_version")))audit.append(project,actor,"ProjectRetrievalIndex",(UUID)active.getFirst().get("id"),"SOURCE_INDEX_VERSION_REQUIRES_REBUILD",correlation,
                Map.of("activeIndexVersion",active.getFirst().get("index_version"),"pendingIndexVersion",index),null,null);
            return active.getFirst();
        }
        @SuppressWarnings("unchecked") Map<String,Object> embedding=(Map<String,Object>)config.body().get("embedding");
        jdbc.update("""
            INSERT INTO project_retrieval_indexes(id,project_id,index_version,parser_version,embedding_provider,embedding_model,dimensions,status,created_by)
            VALUES(?,?,?,?,?,?,?,'HISTORICAL',?) ON CONFLICT(project_id,index_version) DO NOTHING
            """,UUID.randomUUID(),project,index,config.parserVersion(),embedding.get("provider"),embedding.get("model"),config.dimensions(),actor);
        var target=jdbc.queryForMap("SELECT * FROM project_retrieval_indexes WHERE project_id=? AND index_version=? FOR UPDATE",project,index);
        if(activate || active.isEmpty()) {
            if(!active.isEmpty() && !target.get("id").equals(active.getFirst().get("id")))
                jdbc.update("UPDATE project_retrieval_indexes SET status='HISTORICAL',updated_at=clock_timestamp() WHERE id=?",active.getFirst().get("id"));
            jdbc.update("UPDATE project_retrieval_indexes SET status='ACTIVE',activated_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=?",target.get("id"));
        }
        return jdbc.queryForMap("SELECT * FROM project_retrieval_indexes WHERE id=?",target.get("id"));
    }
}
