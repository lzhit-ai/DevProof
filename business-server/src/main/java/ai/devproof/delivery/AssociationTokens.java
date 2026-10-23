package ai.devproof.delivery;

import java.util.*;
import java.util.regex.Pattern;

/** The existing token-overlap-v1 rule; scores describe association candidates only. */
public final class AssociationTokens {
    public static final String VERSION="token-overlap-v1";
    private static final Pattern ASCII=Pattern.compile("[a-z0-9][a-z0-9_-]{1,}"),HAN=Pattern.compile("[\\u4e00-\\u9fff]{2,}");
    private AssociationTokens() {}
    public static Set<String> extract(String raw) {
        String text=raw.toLowerCase(Locale.ROOT); int count=text.codePointCount(0,text.length());
        if(count>30000)text=text.substring(0,text.offsetByCodePoints(0,30000));
        Set<String> result=new TreeSet<>(); var ascii=ASCII.matcher(text);
        while(ascii.find())result.add(ascii.group());
        var han=HAN.matcher(text);
        while(han.find()) { String segment=han.group(); for(int i=0;i<segment.length()-1;i++)result.add(segment.substring(i,i+2)); }
        return result;
    }
    public static double confidence(int overlap) { return Math.round(Math.min(.8,.35+.07*Math.min(overlap,6))*100)/100.0; }
}
