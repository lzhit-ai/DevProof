package ai.devproof.infrastructure;

import java.sql.Timestamp;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

/** Stable UTC microseconds, matching the Python representation used in frozen manifests. */
public final class UtcTime {
    private static final DateTimeFormatter SECOND=DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss").withZone(ZoneOffset.UTC);
    private UtcTime() {}
    public static String iso(Object value) {
        if(value==null)return null;
        Instant at=value instanceof Timestamp stamp?stamp.toInstant():(Instant)value;
        int micro=at.getNano()/1000;
        return SECOND.format(at)+(micro==0?"":String.format(Locale.ROOT,".%06d",micro))+"Z";
    }
}
