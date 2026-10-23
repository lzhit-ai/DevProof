package ai.devproof.infrastructure;

import java.util.*;

/** Input extraction for byte-preserving idempotent commands. */
public final class ApiInput {
    private ApiInput() {}
    @SuppressWarnings("unchecked") public static Map<String,Object> object(byte[] raw) {
        Object value=Json.read(raw); if(!(value instanceof Map<?,?> map))throw invalid(); return (Map<String,Object>)map;
    }
    public static String text(Map<String,Object> body,String key,int min,int max) {
        if(!(body.get(key) instanceof String value) || value.codePointCount(0,value.length())<min || value.codePointCount(0,value.length())>max)throw invalid(); return value;
    }
    public static String optionalText(Map<String,Object> body,String key,int max) { return body.get(key)==null?null:text(body,key,0,max); }
    public static UUID uuid(Object value) { try { return UUID.fromString((String)value); } catch(RuntimeException e) { throw invalid(); } }
    public static UUID optionalUuid(Map<String,Object> body,String key) { return body.get(key)==null?null:uuid(body.get(key)); }
    public static List<UUID> uuids(Map<String,Object> body,String key,int max) {
        if(!body.containsKey(key))return List.of();
        if(!(body.get(key) instanceof List<?> values) || values.size()>max)throw invalid(); return values.stream().map(ApiInput::uuid).toList();
    }
    public static ApiProblem invalid() { return new ApiProblem(422,"INPUT_INVALID","请求字段不符合约束"); }
}
