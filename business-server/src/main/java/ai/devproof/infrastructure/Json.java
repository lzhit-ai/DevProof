package ai.devproof.infrastructure;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.core.json.JsonWriteFeature;

public final class Json {
    private static final JsonMapper MAPPER = JsonMapper.builder().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS).build();
    private static final JsonMapper CANONICAL = JsonMapper.builder().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
        .disable(JsonWriteFeature.ESCAPE_FORWARD_SLASHES,JsonWriteFeature.ESCAPE_NON_ASCII,JsonWriteFeature.WRITE_HEX_UPPER_CASE).build();
    private Json() {}

    public static String write(Object value) { return MAPPER.writeValueAsString(value); }
    public static String canonical(Object value) { return CANONICAL.writeValueAsString(value); }
    public static Object read(String text) { return MAPPER.readValue(text, Object.class); }
    public static Object read(byte[] bytes) { return MAPPER.readValue(bytes,Object.class); }
    public static <T> T read(String text,Class<T> type) { return MAPPER.readValue(text,type); }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> object(String text) {
        Object value = read(text);
        if (!(value instanceof Map<?, ?>)) throw new IllegalArgumentException("JSON object required");
        return (Map<String, Object>) value;
    }

    public static Map<String, Object> error(String code, String message, String correlationId) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("code", code); result.put("message", message);
        result.put("correlationId", correlationId); result.put("details", null);
        return result;
    }

    public static String hash(String value) {
        return hash(value.getBytes(StandardCharsets.UTF_8));
    }
    public static String hash(byte[] value) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value));
        } catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
