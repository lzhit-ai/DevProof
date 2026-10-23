package ai.devproof.infrastructure;

import java.util.regex.Pattern;

public final class SafeExcerpt {
    private static final Pattern BEARER=Pattern.compile("(?i)bearer\\s+[A-Za-z0-9._~+/-]+",Pattern.UNICODE_CHARACTER_CLASS);
    private static final Pattern ASSIGNMENT=Pattern.compile("(?i)\\b(api[_-]?key|password|passwd|secret|token|authorization)\\b(\\s*[:=]\\s*)([^\\s,;]+)",Pattern.UNICODE_CHARACTER_CLASS);
    private SafeExcerpt() {}
    public static String text(String raw,int limit) {
        String value=ASSIGNMENT.matcher(BEARER.matcher(raw).replaceAll("Bearer [REDACTED]")).replaceAll(match->match.group(1)+match.group(2)+"[REDACTED]");
        int length=value.codePointCount(0,value.length());
        return length<=limit?value:value.substring(0,value.offsetByCodePoints(0,limit));
    }
}
