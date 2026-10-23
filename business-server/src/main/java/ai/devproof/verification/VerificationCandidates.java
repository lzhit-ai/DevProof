package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.util.*;

/** The versioned result structure is separate from citation and business validation. */
public record VerificationCandidates(List<Finding> findings,List<Challenge> challenges,List<Link> links,List<Custom> customResults,List<Coverage> coverage,List<String> nodeErrors) {
    public record Finding(String key,UUID evidence,List<UUID> claims,String kind,String severity,String title,String problem,String trigger,String recommendation,double confidence) {}
    public record Challenge(String key,String verdict,String reason,List<UUID> evidence) {}
    public record Link(UUID claim,UUID evidence,String relation,String reason) {}
    public record Custom(String key,List<Link> links) {}
    public record Coverage(String kind,String reference,String state,String reason,Map<String,Object> details) {}
    public static VerificationCandidates parse(Map<String,Object> raw) {
        fields(raw,"schemaVersion","findings","challenges","links","customResults","coverage","nodeErrors");
        if(!"verification-result-v1".equals(raw.get("schemaVersion")))throw invalid();
        List<Finding> findings=new ArrayList<>();
        for(Map<String,Object> item:objects(raw,"findings",100)) {
            fields(item,"findingKey","evidenceId","relatedClaimIds","findingKind","severity","title","problem","triggerScenario","recommendation","confidence");
            Object value=item.get("confidence");
            if(!(value instanceof Number number) || !Double.isFinite(number.doubleValue()) || number.doubleValue()<0 || number.doubleValue()>1)throw invalid();
            findings.add(new Finding(text(item,"findingKey",64),uuid(item.get("evidenceId")),uuids(item,"relatedClaimIds",20),
                choice(item,"findingKind",Set.of("BUG","SECURITY","PERFORMANCE","RELIABILITY","MAINTAINABILITY","TEST_GAP")),choice(item,"severity",Set.of("CRITICAL","HIGH","MEDIUM","LOW")),
                text(item,"title",240),text(item,"problem",4000),text(item,"triggerScenario",3000),text(item,"recommendation",4000),number.doubleValue()));
        }
        List<Challenge> challenges=new ArrayList<>();
        for(Map<String,Object> item:objects(raw,"challenges",100)) {
            fields(item,"findingKey","verdict","reason","evidenceIds"); List<UUID> evidence=uuids(item,"evidenceIds",20); if(evidence.isEmpty())throw invalid();
            challenges.add(new Challenge(text(item,"findingKey",64),choice(item,"verdict",Set.of("SUPPORTED","UNSUPPORTED","NEEDS_HUMAN")),text(item,"reason",4000),evidence));
        }
        List<Custom> custom=new ArrayList<>();
        for(Map<String,Object> item:objects(raw,"customResults",100)) { fields(item,"capabilityKey","links"); custom.add(new Custom(text(item,"capabilityKey",96),links(item,100))); }
        List<Coverage> coverage=new ArrayList<>();
        for(Map<String,Object> item:objects(raw,"coverage",150)) {
            fields(item,"scopeKind","scopeRef","state","reasonCode","details");
            Map<String,Object> details=object(item.get("details")); if(Json.write(details).length()>131072)throw invalid();
            coverage.add(new Coverage(choice(item,"scopeKind",Set.of("CODE_REVIEW","FINDING_CHALLENGE","MODEL","AGENT","CONTEXT_SUPPLEMENT")),text(item,"scopeRef",96),
                choice(item,"state",Set.of("ANALYZED","PARTIAL","UNAVAILABLE","SKIPPED","NOT_APPLICABLE")),item.get("reasonCode")==null?null:text(item,"reasonCode",128),details));
        }
        List<String> errors=new ArrayList<>();
        for(Object value:array(raw,"nodeErrors",200)) { if(!(value instanceof String code) || code.isBlank() || code.length()>256)throw invalid(); errors.add(code); }
        return new VerificationCandidates(findings,challenges,links(raw,200),custom,coverage,errors);
    }
    private static List<Link> links(Map<String,Object> raw,int max) {
        List<Link> links=new ArrayList<>();
        for(Map<String,Object> item:objects(raw,"links",max)) { fields(item,"claimId","evidenceId","relation","rationale"); links.add(new Link(uuid(item.get("claimId")),uuid(item.get("evidenceId")),choice(item,"relation",Set.of("SUPPORTS","CONTRADICTS","CONTEXT_ONLY")),text(item,"rationale",1000))); }
        return links;
    }
    private static List<UUID> uuids(Map<String,Object> raw,String key,int max) { return array(raw,key,max).stream().map(VerificationCandidates::uuid).toList(); }
    static UUID uuid(Object value) { try { return UUID.fromString((String)value); } catch(RuntimeException e) { throw invalid(); } }
    private static void fields(Map<String,Object> value,String... keys) { if(!value.keySet().equals(Set.of(keys)))throw invalid(); }
    private static String text(Map<String,Object> value,String key,int max) {
        if(!(value.get(key) instanceof String text) || text.isEmpty() || text.codePointCount(0,text.length())>max)throw invalid(); return text;
    }
    private static String choice(Map<String,Object> value,String key,Set<String> values) { String text=text(value,key,64); if(!values.contains(text))throw invalid(); return text; }
    private static List<?> array(Map<String,Object> value,String key,int max) { if(!(value.get(key) instanceof List<?> list) || list.size()>max)throw invalid(); return list; }
    private static List<Map<String,Object>> objects(Map<String,Object> value,String key,int max) { return array(value,key,max).stream().map(VerificationCandidates::object).toList(); }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object value) { if(!(value instanceof Map<?,?> map))throw invalid(); return (Map<String,Object>)map; }
    private static ApiProblem invalid() { return new ApiProblem(422,"RESULT_SCHEMA_INVALID","核验候选不符合 verification-result-v1"); }
}
