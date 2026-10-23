package ai.devproof.report;

import ai.devproof.infrastructure.Json;
import java.sql.Timestamp;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.*;
import tools.jackson.core.json.JsonWriteFeature;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.json.JsonMapper;

/** v1 hashes preserve ordered result arrays and Python's UTF-8/sorted-key JSON. */
final class ReportCanonical {
    private static final JsonMapper CANONICAL=JsonMapper.builder().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
        .disable(JsonWriteFeature.ESCAPE_FORWARD_SLASHES,JsonWriteFeature.ESCAPE_NON_ASCII,JsonWriteFeature.WRITE_HEX_UPPER_CASE).build();
    private ReportCanonical() {}
    static String hash(List<Map<String,Object>> results,String note,Map<String,Object> dispositions) {
        return Json.hash(CANONICAL.writeValueAsString(Map.of("results",results,"editorialNote",note,"dispositions",dispositions)));
    }
    static Map<String,Object> decision(Map<String,Object> row) {
        if(row==null)return null;
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("id",row.get("id").toString()); result.put("decision",row.get("decision")); result.put("note",row.get("note"));
        result.put("actorId",row.get("actor_id").toString()); result.put("createdAt",timestamp((Timestamp)row.get("created_at"))); return result;
    }
    static String timestamp(Timestamp value) {
        if(value==null)return null;
        var time=value.toInstant().atOffset(ZoneOffset.UTC);
        String seconds=DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss").format(time);
        return seconds+(time.getNano()==0?"":"."+String.format(Locale.ROOT,"%06d",time.getNano()/1000))+"+00:00";
    }
    static Map<String,Object> result(Map<String,Object> row,Map<String,Object> decision) {
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("status",row.get("status")); result.put("reason",row.get("reason")); result.put("humanDecision",decision); return result;
    }
    static String cycleStatus(List<Map<String,Object>> results) {
        if(results.isEmpty() || results.stream().allMatch(row->Set.of("NOT_PROVEN","NOT_ANALYZED").contains(row.get("status"))))return "NEEDS_EVIDENCE";
        if(results.stream().anyMatch(row->Boolean.TRUE.equals(row.get("requires_human_confirmation"))))return "NEEDS_CONFIRMATION";
        return "DRAFT_READY";
    }
    static String deliveryStatus(List<Map<String,Object>> items) {
        List<String> statuses=new ArrayList<>();
        for(Map<String,Object> item:items) {
            Map<String,Object> result=Json.object((String)item.get("result_json"));
            Object human=result.get("humanDecision"); String status=(String)result.get("status");
            if(human instanceof Map<?,?> decision) {
                status=switch(String.valueOf(decision.get("decision"))) {
                    case "CONFIRM_SUPPORT"->"CONFIRMED"; case "CONFIRM_PARTIAL"->"PARTIALLY_SUPPORTED";
                    case "CONFIRM_INSUFFICIENT","RETURN_FOR_EVIDENCE"->"INSUFFICIENT_EVIDENCE"; default->status;
                };
            }
            statuses.add(status);
        }
        if(!statuses.isEmpty() && statuses.stream().allMatch(value->Set.of("SUPPORTED","CONFIRMED").contains(value)))return "CONFIRMED";
        if(statuses.stream().anyMatch(value->Set.of("CONFLICT","CONFLICTING").contains(value)))return "CONFLICT";
        if(statuses.isEmpty() || statuses.stream().allMatch(value->Set.of("INSUFFICIENT_EVIDENCE","NOT_PROVEN","NOT_ANALYZED").contains(value)))return "INSUFFICIENT_EVIDENCE";
        return "PARTIALLY_SUPPORTED";
    }
}
