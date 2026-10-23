package ai.devproof.verification;

import java.util.*;
import java.util.regex.Pattern;

/** Materialized, deterministic business rules; no model, database, Git or HTTP dependencies. */
public final class VerificationRules {
    public static final String VERSION="delivery-verdict-v2";
    private static final Pattern ASCII=Pattern.compile("[A-Za-z_][A-Za-z0-9_]{3,}"), KEY=Pattern.compile("[A-Za-z]{2,}-\\d+",Pattern.UNICODE_CHARACTER_CLASS), CJK=Pattern.compile("[\\u4e00-\\u9fff]{2,}");
    private static final Set<String> STOP=Set.of("this","that","with","from","true","false","none","null","return","class","function","const","import","async","await");
    private static final Set<String> CAPTURE_ERRORS=Set.of("GIT_ARTIFACT_MISSING","GIT_ARTIFACT_UNAVAILABLE","GIT_ARTIFACT_HASH_MISMATCH");
    public record Scope(UUID projectId,UUID snapshotId) {}
    public record Claim(UUID id,String text,int authorityLevel) {}
    public record Evidence(UUID id,UUID projectId,UUID snapshotId,String sourceType,String kind,String precision,String excerpt,Map<String,Object> locator) {}
    public record Link(UUID claimId,UUID evidenceId,String relation,String reason,double confidence,String producer,boolean requiresHumanConfirmation) {}
    public record Verdict(UUID claimId,String status,String reason,List<UUID> evidenceIds,boolean requiresHumanConfirmation) {}
    public record Risk(UUID claimId,UUID evidenceId,String severity,String category,String recommendation) {}
    public record Outcome(List<Link> links,List<Verdict> verdicts,List<Risk> risks,int rejectedModelLinks) {}
    private record LinkKey(UUID claimId,UUID evidenceId,String relation) {}
    private VerificationRules() {}

    public static Set<String> tokens(String text) {
        Set<String> result=new HashSet<>();
        for(Pattern pattern:List.of(ASCII,KEY,CJK)) {
            var matcher=pattern.matcher(text);
            while(matcher.find())result.add(matcher.group().toLowerCase(Locale.ROOT));
        }
        result.removeAll(STOP); return result;
    }
    public static boolean citable(Scope scope,Evidence evidence) {
        return scope.projectId().equals(evidence.projectId()) && scope.snapshotId().equals(evidence.snapshotId())
            && !"TOOL".equals(evidence.sourceType()) && !"HTTP_QUERY".equals(evidence.kind());
    }
    public static boolean diffEvidence(Scope scope,Evidence evidence) {
        return citable(scope,evidence) && "CODE".equals(evidence.sourceType()) && "GIT_DIFF_HUNK".equals(evidence.kind()) && "EXACT".equals(evidence.precision());
    }
    public static Outcome reconcile(Scope scope,List<Claim> claims,List<Evidence> evidence,List<Link> modelCandidates,List<String> nodeErrors,boolean riskScan) {
        Map<UUID,Evidence> allowed=new LinkedHashMap<>();
        for(Evidence item:evidence)if(citable(scope,item))allowed.put(item.id(),item);
        Set<UUID> claimIds=new HashSet<>(); for(Claim claim:claims)claimIds.add(claim.id());
        Map<LinkKey,Link> links=new LinkedHashMap<>();
        for(Claim claim:claims) {
            Set<String> claimTokens=tokens(claim.text());
            for(Evidence item:allowed.values()) {
                boolean manual="MANUAL".equals(item.sourceType());
                if(!manual && !diffEvidence(scope,item) && !Set.of("TEST","BUILD").contains(item.sourceType()))continue;
                Set<String> overlap=new TreeSet<>(claimTokens); overlap.retainAll(tokens(item.excerpt()));
                if(overlap.isEmpty())continue;
                Object exit=item.locator().get("exitCode");
                boolean conflict=!manual && Set.of("TEST","BUILD").contains(item.sourceType()) && exit instanceof Number number && number.doubleValue()!=0;
                String relation=conflict?"CONTRADICTS":"SUPPORTS";
                String prefix=manual?"人工补证包含与核验目标重叠的标识符：":conflict?"外部 "+item.sourceType()+" 的非零退出码与目标冲突；标识符命中：":"确定性标识符命中：";
                Link link=new Link(claim.id(),item.id(),relation,prefix+String.join(", ",overlap.stream().limit(5).toList()),manual?0.5:0.75,manual?"HUMAN":"DETERMINISTIC",conflict);
                links.putIfAbsent(new LinkKey(claim.id(),item.id(),relation),link);
            }
        }
        int rejected=0;
        for(Link candidate:modelCandidates) {
            Evidence item=allowed.get(candidate.evidenceId());
            if(!claimIds.contains(candidate.claimId()) || item==null || !(diffEvidence(scope,item) || Set.of("TEST","BUILD","MANUAL").contains(item.sourceType()))
                || !Set.of("SUPPORTS","CONTRADICTS","CONTEXT_ONLY").contains(candidate.relation()) || !"MODEL".equals(candidate.producer())) { rejected++; continue; }
            // A model proposal cannot overwrite a prior deterministic/human relation.
            Link accepted=new Link(candidate.claimId(),candidate.evidenceId(),candidate.relation(),candidate.reason(),0.5,"MODEL","CONTRADICTS".equals(candidate.relation()));
            links.putIfAbsent(new LinkKey(candidate.claimId(),candidate.evidenceId(),candidate.relation()),accepted);
        }
        List<Verdict> verdicts=new ArrayList<>(); List<Risk> risks=new ArrayList<>();
        boolean captureUnavailable=nodeErrors.stream().anyMatch(CAPTURE_ERRORS::contains), modelUnavailable=nodeErrors.stream().anyMatch(code->code.startsWith("MODEL_"));
        for(Claim claim:claims) {
            List<Link> own=links.values().stream().filter(link->claim.id().equals(link.claimId())).toList();
            List<Link> deterministic=supports(own,"DETERMINISTIC"), human=supports(own,"HUMAN"), model=supports(own,"MODEL");
            List<Link> conflicts=own.stream().filter(link->"CONTRADICTS".equals(link.relation()) && Set.of("MODEL","DETERMINISTIC").contains(link.producer())).toList();
            List<UUID> ids=new ArrayList<>();
            for(List<Link> group:List.of(deterministic,conflicts,human,model))for(Link link:group)ids.add(link.evidenceId());
            String status,reason; boolean requiresHuman=false;
            if(!conflicts.isEmpty()) {
                status="CONFLICTING"; reason="存在与冻结代码证据关联的反驳结论，需要核对业务语义"; requiresHuman=true;
                if(riskScan)for(Link conflict:conflicts)risks.add(new Risk(claim.id(),conflict.evidenceId(),claim.authorityLevel()>=3?"HIGH":"MEDIUM","EVIDENCE_CONFLICT","复核冲突证据并补充与冻结提交绑定的可追溯材料"));
            } else if(model.stream().anyMatch(link->diffEvidence(scope,allowed.get(link.evidenceId())))) {
                status="SUPPORTED"; reason="模型分析结果已绑定到当前冻结 Diff Hunk；必要代码上下文仅用于解释，不作为独立证据";
            } else if(!deterministic.isEmpty()) {
                status="PARTIALLY_SUPPORTED"; reason="已发现冻结 Git 范围内的直接代码标识符命中，但尚未形成足以证明完整目标的语义证据";
            } else if(!human.isEmpty()) {
                status="PARTIALLY_SUPPORTED"; reason="已关联人工补证；该补证不能单独证明本次冻结 PR 的代码交付范围";
            } else if(captureUnavailable || (modelUnavailable && deterministic.isEmpty())) {
                status="NOT_ANALYZED"; reason="冻结代码输入或必要模型分析不可用，当前不能完成该目标的核验";
            } else {
                status="NOT_PROVEN"; reason="已完成当前冻结代码范围分析，但没有足够的直接证据证明该交付目标";
            }
            verdicts.add(new Verdict(claim.id(),status,reason,List.copyOf(ids),requiresHuman));
        }
        return new Outcome(List.copyOf(links.values()),List.copyOf(verdicts),List.copyOf(risks),rejected);
    }
    private static List<Link> supports(List<Link> links,String producer) {
        return links.stream().filter(link->"SUPPORTS".equals(link.relation()) && producer.equals(link.producer())).toList();
    }
}
