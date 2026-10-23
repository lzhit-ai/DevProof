package ai.devproof.retrieval;

import ai.devproof.infrastructure.UnicodeText;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;

/** Existing RRF and business metadata weights; stable ordering is applied after six-digit rounding. */
public final class RetrievalRanking {
    private RetrievalRanking() {}
    public record Candidate(UUID chunk,UUID source,int index,Integer ftsRank,Double ftsScore,Integer vectorRank,Double vectorScore,String hash) {}
    public record Signals(double rrf,double normalizedRrf,double role,double quality,double score) {}
    public record Quality(String precision,Double ocr) {}
    public static Map<UUID,Signals> rank(List<Candidate> candidates,Map<UUID,String> roles,List<String> preferred,Map<UUID,Quality> quality) {
        Set<String> requested=roles(preferred); Map<UUID,Double> raw=new HashMap<>(); double max=0;
        for(var candidate:candidates) { double score=rrf(candidate); raw.put(candidate.chunk(),score); max=Math.max(max,score); }
        Map<UUID,Signals> result=new HashMap<>();
        for(var candidate:candidates) {
            double rrf=raw.get(candidate.chunk()),normalized=max==0?0:rrf/max;
            double match=!requested.isEmpty() && requested.contains(normalize(roles.getOrDefault(candidate.source(),"")))?1:0;
            Quality metadata=quality.getOrDefault(candidate.chunk(),new Quality("UNAVAILABLE",null));
            double evidence=quality(metadata.precision(),metadata.ocr());
            result.put(candidate.chunk(),new Signals(rrf,normalized,match,evidence,0.75*normalized+0.15*match+0.10*evidence));
        }
        return result;
    }
    public static List<String> reasons(Candidate candidate,String role,List<String> preferred,String precision,Double ocr) {
        List<String> result=new ArrayList<>(); result.add(candidate.ftsRank()!=null && candidate.vectorRank()!=null?"双路召回命中":"单路召回命中");
        var requested=roles(preferred);
        if(!requested.isEmpty())result.add(requested.contains(normalize(role))?"匹配指定资料角色":"未匹配指定资料角色");
        String locator=switch(precision) { case "EXACT"->"精确定位"; case "APPROXIMATE"->"近似定位"; default->"定位不可用"; };
        String extraction=ocr==null?"未提供 OCR 置信度，不降权":"OCR 置信度 "+new BigDecimal(clamp(ocr)).setScale(2,RoundingMode.HALF_EVEN).toPlainString();
        result.add("证据质量："+locator+"；"+extraction); return result;
    }
    public static double round(double value) { return new BigDecimal(value).setScale(6,RoundingMode.HALF_EVEN).doubleValue(); }
    private static double rrf(Candidate candidate) { return (candidate.ftsRank()==null?0:1.0/(60+candidate.ftsRank()))+(candidate.vectorRank()==null?0:1.0/(60+candidate.vectorRank())); }
    private static double quality(String precision,Double ocr) {
        double locator=switch(precision) { case "EXACT"->1; case "APPROXIMATE"->0.5; default->0; };
        return 0.6*locator+0.4*(ocr==null?1:clamp(ocr));
    }
    private static double clamp(double value) { return Double.isNaN(value)?1:Math.max(0,Math.min(1,value)); }
    private static String normalize(String value) { return UnicodeText.casefold(UnicodeText.strip(value)); }
    private static Set<String> roles(List<String> values) {
        Set<String> result=new HashSet<>(); for(String value:values) { String role=normalize(value); if(!role.isEmpty())result.add(role); } return result;
    }
}
