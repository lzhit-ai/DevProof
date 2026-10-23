package ai.devproof.knowledge;

import ai.devproof.infrastructure.Json;
import java.sql.Timestamp;
import java.util.*;

final class KnowledgeViews {
    private KnowledgeViews() {}
    static Map<String,Object> fields(Map<String,Object> row,String... keys) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(String key:keys) { Object value=row.get(key); result.put(key,value instanceof Timestamp stamp?stamp.toInstant().toString():value); }
        return result;
    }
    static Map<String,Object> object(Object value) { return value==null?Map.of():Json.object(value.toString()); }
    static Map<String,Object> source(Map<String,Object> row) {
        var view=fields(row,"id","project_id","logical_name","source_role","revision_no","content_hash","media_type","original_filename",
            "processing_status","parser_version","failure_code","ocr_confidence","knowledge_base_id","force_ocr","created_at","updated_at","in_snapshot","ingestion_job_status");
        view.put("extraction_metadata",object(row.get("extraction_metadata"))); return view;
    }
}
