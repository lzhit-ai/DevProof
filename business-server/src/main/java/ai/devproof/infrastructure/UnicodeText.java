package ai.devproof.infrastructure;

/** Whitespace trimming compatible with existing Python-authored business text. */
public final class UnicodeText {
    private static final java.util.Map<String,Object> CASEFOLD=casefoldData();
    private UnicodeText() {}
    public static String strip(String value) {
        int start=0,end=value.length();
        while(start<end && whitespace(value.codePointAt(start)))start+=Character.charCount(value.codePointAt(start));
        while(end>start && whitespace(value.codePointBefore(end)))end-=Character.charCount(value.codePointBefore(end));
        return value.substring(start,end);
    }
    private static boolean whitespace(int codePoint) { return Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint) || codePoint==0x85; }
    /** Full Unicode folding preserves the existing Python source-role matching semantics. */
    public static String casefold(String value) {
        StringBuilder result=new StringBuilder();
        value.codePoints().forEach(point->{ Object mapped=CASEFOLD.get(Integer.toString(point));
            if(mapped instanceof String text)result.append(text); else result.appendCodePoint(point); });
        return result.toString();
    }
    @SuppressWarnings("unchecked") private static java.util.Map<String,Object> casefoldData() {
        try(var stream=UnicodeText.class.getResourceAsStream("/contracts/unicode-casefold.json")) {
            if(stream==null)throw new IllegalStateException("Unicode compatibility data missing");
            return java.util.Map.copyOf((java.util.Map<String,Object>)Json.object(new String(stream.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8)).get("casefold"));
        } catch(java.io.IOException error) { throw new IllegalStateException("Unicode compatibility data unavailable",error); }
    }
}
