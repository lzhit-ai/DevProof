package ai.devproof.source;

import ai.devproof.infrastructure.Json;
import java.sql.Timestamp;
import java.util.*;

final class SourceViews {
    private SourceViews() {}
    static Map<String,Object> connection(Map<String,Object> row) {
        Map<String,Object> result=fields(row,"id","project_id","provider","name","repository_slug","is_active","created_at"); result.put("secret_ref_configured",row.get("secret_ref")!=null); return result;
    }
    static Map<String,Object> sync(Map<String,Object> row) {
        Map<String,Object> result=fields(row,"id","connection_id","status","started_at","finished_at","fetched_count","changed_count","page_count","error_code","error_message");
        result.put("continuation_cursor",Json.object((String)row.get("cursor_json")));
        Object retry="RUNNING".equals(row.get("status")) && row.get("error_code")!=null?row.get("available_at"):null;
        result.put("next_retry_at",retry instanceof Timestamp time?time.toInstant().toString():retry);
        return result;
    }
    static Map<String,Object> fields(Map<String,Object> row,String... names) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(String name:names) { Object value=row.get(name); result.put(name,value instanceof Timestamp time?time.toInstant().toString():value); }
        return result;
    }
}
