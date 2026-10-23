package ai.devproof.retrieval;

import ai.devproof.infrastructure.Json;
import ai.devproof.infrastructure.ApiProblem;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.*;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** FTS/simple plus pgvector. Both lanes can rank only the snapshot's actual, hash-matching document evidence. */
@Component
public class PostgresHybridRetriever {
    private final JdbcTemplate jdbc;
    private static final String COLUMNS="c.id,c.source_revision_id,c.chunk_index,c.content,c.text_hash";
    private static final String SCOPE="""
        c.source_revision_id=ANY(?) AND EXISTS(SELECT 1 FROM evidence_items e WHERE e.id=ANY(?) AND e.content_hash=c.text_hash
          AND ((e.locator->>'sourceRevisionId'=c.source_revision_id::text AND e.locator->>'chunkIndex'=c.chunk_index::text)
            OR e.locator->>'chunkId'=c.id::text))
        """;
    private record Identity(UUID source,int index) {}
    public PostgresHybridRetriever(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public List<RetrievalRanking.Candidate> search(List<UUID> sources,List<UUID> evidence,String query,int limit,List<Double> embedding,String index) {
        LinkedHashMap<Identity,RetrievalRanking.Candidate> candidates=new LinkedHashMap<>();
        String fts="SELECT "+COLUMNS+",ts_rank_cd(to_tsvector('simple',c.content),websearch_to_tsquery('simple',?)) AS score FROM document_chunks c WHERE "+SCOPE+
            " AND to_tsvector('simple',c.content) @@ websearch_to_tsquery('simple',?) ORDER BY score DESC LIMIT ?";
        List<Map<String,Object>> rows=rows(fts,sources,evidence,query,limit*12,null,null);
        for(var row:rows) {
            var identity=identity(row); if(candidates.containsKey(identity))continue;
            candidates.put(identity,candidate(row,candidates.size()+1,number(row.get("score")),null,null));
            if(candidates.size()>=limit*3)break;
        }
        if(embedding!=null) {
            String vector="SELECT "+COLUMNS+",c.embedding <=> CAST(? AS vector) AS score FROM document_chunks c WHERE "+SCOPE+
                " AND c.embedding IS NOT NULL"+(index==null?"":" AND c.index_version=?")+" ORDER BY score LIMIT ?";
            int position=0;
            for(var row:rows(vector,sources,evidence,null,limit*12,embedding,index)) {
                var identity=identity(row); var prior=candidates.get(identity);
                if(prior!=null && prior.vectorRank()!=null)continue; position++;
                Double distance=number(row.get("score"));
                // Preserve the former score-or-1 behavior; fusion itself uses ranks, not these raw scales.
                double score=1-(distance==null || distance==0?1:distance);
                candidates.put(identity,candidate(row,prior==null?null:prior.ftsRank(),prior==null?null:prior.ftsScore(),position,score));
                if(position>=limit*3)break;
            }
        }
        if(candidates.isEmpty()) {
            literal(sources,evidence,query,candidates);
        }
        return List.copyOf(candidates.values());
    }
    private void literal(List<UUID> sources,List<UUID> evidence,String query,LinkedHashMap<Identity,RetrievalRanking.Candidate> candidates) {
        jdbc.execute((ConnectionCallback<Void>) connection->{
            java.sql.Array sourceIds=null,evidenceIds=null;
            try {
                sourceIds=uuidArray(connection,sources); evidenceIds=uuidArray(connection,evidence);
                try(var statement=connection.prepareStatement("SELECT "+COLUMNS+" FROM document_chunks c WHERE "+SCOPE)) {
                    statement.setQueryTimeout(30); statement.setFetchSize(128); statement.setArray(1,sourceIds); statement.setArray(2,evidenceIds);
                    String needle=query.toLowerCase(Locale.ROOT);
                    try(var result=statement.executeQuery()) {
                        while(result.next()) {
                            String content=result.getString("content"); if(!content.toLowerCase(Locale.ROOT).contains(needle))continue;
                            Map<String,Object> row=new HashMap<>(); row.put("id",result.getObject("id")); row.put("source_revision_id",result.getObject("source_revision_id"));
                            row.put("chunk_index",result.getInt("chunk_index")); row.put("content",content); row.put("text_hash",result.getString("text_hash"));
                            if(!candidates.containsKey(identity(row)))candidates.put(identity(row),candidate(row,1,0.0,null,null));
                        }
                    }
                }
            } finally { if(sourceIds!=null)sourceIds.free(); if(evidenceIds!=null)evidenceIds.free(); }
            return null;
        });
    }
    private List<Map<String,Object>> rows(String sql,List<UUID> sources,List<UUID> evidence,String query,int limit,List<Double> embedding,String index) {
        return jdbc.execute((ConnectionCallback<List<Map<String,Object>>>) connection->{
            java.sql.Array sourceIds=null,evidenceIds=null;
            try {
                sourceIds=uuidArray(connection,sources); evidenceIds=uuidArray(connection,evidence);
                try(var statement=connection.prepareStatement(sql)) {
                statement.setQueryTimeout(30); int parameter=1;
                if(query!=null)statement.setString(parameter++,query);
                if(embedding!=null)statement.setString(parameter++,Json.canonical(embedding));
                statement.setArray(parameter++,sourceIds); statement.setArray(parameter++,evidenceIds);
                if(query!=null)statement.setString(parameter++,query);
                if(embedding!=null && index!=null)statement.setString(parameter++,index);
                if(limit>0)statement.setInt(parameter,limit);
                try(var result=statement.executeQuery()) {
                    List<Map<String,Object>> output=new ArrayList<>(); var metadata=result.getMetaData();
                    while(result.next()) { Map<String,Object> row=new HashMap<>(); for(int column=1;column<=metadata.getColumnCount();column++)row.put(metadata.getColumnLabel(column),result.getObject(column)); output.add(row); }
                    return output;
                }
                }
            } finally {
                if(sourceIds!=null)sourceIds.free(); if(evidenceIds!=null)evidenceIds.free();
            }
        });
    }
    private static java.sql.Array uuidArray(Connection connection,List<UUID> values) throws SQLException { return connection.createArrayOf("uuid",values.toArray()); }
    private static Identity identity(Map<String,Object> row) { return new Identity((UUID)row.get("source_revision_id"),((Number)row.get("chunk_index")).intValue()); }
    private static Double number(Object value) { return value==null?null:((Number)value).doubleValue(); }
    private static RetrievalRanking.Candidate candidate(Map<String,Object> row,Integer fts,Double ftsScore,Integer vector,Double vectorScore) {
        if(!Json.hash((String)row.get("content")).equals(row.get("text_hash")))throw new ApiProblem(409,"SOURCE_HASH_MISMATCH","检索分块的实际内容与冻结证据摘要不一致");
        var key=identity(row); return new RetrievalRanking.Candidate((UUID)row.get("id"),key.source(),key.index(),fts,ftsScore,vector,vectorScore,(String)row.get("text_hash"));
    }
}
