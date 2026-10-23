package ai.devproof.verification;

import ai.devproof.agentjob.AgentResultConsumer;
import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Scope validation, candidate persistence, final rules and terminal states commit together. */
@Component
public class VerificationResultConsumer implements AgentResultConsumer {
    private final VerificationExecutionMapper data;
    private final InputSnapshotMapper inputs;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final JdbcTemplate jdbc;
    public VerificationResultConsumer(VerificationExecutionMapper data,InputSnapshotMapper inputs,ProjectAccess access,BusinessOwnership owners,JdbcTemplate jdbc) {
        this.data=data; this.inputs=inputs; this.access=access; this.owners=owners; this.jdbc=jdbc;
    }
    public boolean supports(String kind) { return "DELIVERY_VERIFY".equals(kind); }
    public String schemaVersion() { return "verification-result-v1"; }
    @SuppressWarnings("unchecked") public void accept(Map<String,Object> task,Map<String,Object> raw,List<UUID> declared) {
        owners.requireJavaVerification(); VerificationCandidates result=VerificationCandidates.parse(raw);
        UUID id=(UUID)task.get("analysis_run_id"), project=(UUID)task.get("project_id"), actor=(UUID)task.get("created_by"), attempt=(UUID)task.get("current_attempt_id");
        access.require(project,actor,"SUBMITTER","ADMIN"); Map<String,Object> run=data.run(id); if(run==null || !"JAVA".equals(run.get("executor_owner")))throw stale();
        UUID snapshot=(UUID)run.get("snapshot_id"), cycle=(UUID)run.get("cycle_id"); inputs.lockCycle(cycle);
        Map<String,Object> current=inputs.cycle(cycle);
        if(!id.equals(current.get("active_run_id")) || !"ANALYZING".equals(current.get("business_status")))throw stale();
        Map<String,Object> payload=Json.object((String)task.get("payload_json"));
        Map<String,Object> ref=(Map<String,Object>)payload.get("inputSnapshotRef");
        if(!snapshot.toString().equals(ref.get("id")) || !run.get("snapshot_hash").equals(ref.get("contentHash")))throw stale();
        Map<String,Object> plan=data.plan(snapshot), expectedPlan=plan==null?null:Map.of("id",plan.get("plan_version_id").toString(),"contentHash",plan.get("plan_content_hash"));
        if(!Objects.equals(expectedPlan,payload.get("planVersionRef")) || !Objects.equals(run.get("plan_version_id"),plan==null?null:plan.get("plan_version_id")) || !Objects.equals(run.get("plan_baseline_hash"),plan==null?null:plan.get("selection_hash")))throw stale();
        VerificationRules.Scope scope=new VerificationRules.Scope(project,snapshot);
        Set<String> granted=new HashSet<>((List<String>)payload.get("allowedEvidenceIds"));
        Map<UUID,VerificationRules.Evidence> evidence=new LinkedHashMap<>();
        for(Map<String,Object> row:data.evidence(snapshot))if(granted.contains(row.get("id").toString())) {
            VerificationRules.Evidence item=new VerificationRules.Evidence((UUID)row.get("id"),(UUID)row.get("project_id"),snapshot,(String)row.get("source_type"),(String)row.get("evidence_kind"),(String)row.get("locator_precision"),(String)row.get("excerpt_safe"),Json.object((String)row.get("locator_json")));
            if(VerificationRules.citable(scope,item))evidence.put(item.id(),item);
        }
        List<VerificationRules.Claim> claims=data.claims(id).stream().map(row->new VerificationRules.Claim((UUID)row.get("id"),(String)row.get("text"),((Number)row.get("authority_level")).intValue())).toList();
        Set<UUID> claimIds=new HashSet<>(); claims.forEach(claim->claimIds.add(claim.id()));
        Set<UUID> referenced=references(result); if(!new HashSet<>(declared).equals(referenced) || !evidence.keySet().containsAll(referenced))throw citation();
        Map<String,UUID> findingIds=new HashMap<>(); Map<String,UUID> findingEvidence=new HashMap<>(); Map<String,UUID> fingerprints=new HashMap<>(); int rejectedFindings=0,rejectedChallenges=0;
        if(!result.findings().isEmpty() && !called(attempt,"CODE_REVIEW"))throw stale();
        for(VerificationCandidates.Finding finding:result.findings()) {
            VerificationRules.Evidence item=evidence.get(finding.evidence());
            if(findingIds.containsKey(finding.key()))throw new ApiProblem(422,"RESULT_SCHEMA_INVALID","发现标识不能重复");
            if(item==null || !VerificationRules.diffEvidence(scope,item) || !claimIds.containsAll(finding.claims())) { rejectedFindings++; continue; }
            String fingerprint=Json.hash(Json.write(Map.of("evidence",finding.evidence().toString(),"claims",finding.claims().stream().map(UUID::toString).sorted().toList(),"kind",finding.kind(),"title",UnicodeText.strip(finding.title()).toLowerCase(Locale.ROOT),"trigger",UnicodeText.strip(finding.trigger()).toLowerCase(Locale.ROOT))));
            UUID findingId=fingerprints.get(fingerprint);
            if(findingId==null) {
                findingId=UUID.randomUUID(); data.finding(findingId,id,item.id(),finding.claims().isEmpty()?null:finding.claims().getFirst(),fingerprint,finding.severity(),finding.kind(),finding.title(),finding.problem(),finding.trigger(),finding.recommendation(),finding.confidence()); fingerprints.put(fingerprint,findingId);
            }
            findingIds.put(finding.key(),findingId); findingEvidence.put(finding.key(),finding.evidence());
        }
        UUID challengeCall=data.challengeCall(attempt); Set<UUID> challenged=new HashSet<>();
        if(!result.challenges().isEmpty() && challengeCall==null)throw stale();
        for(VerificationCandidates.Challenge challenge:result.challenges()) {
            UUID finding=findingIds.get(challenge.key()); List<UUID> refs=challenge.evidence().stream().distinct().toList();
            if(finding==null || challenged.contains(finding) || !refs.contains(findingEvidence.get(challenge.key())) || refs.stream().anyMatch(key->!VerificationRules.diffEvidence(scope,evidence.get(key)))) { rejectedChallenges++; continue; }
            challenged.add(finding);
            data.challenge(UUID.randomUUID(),id,finding,Json.hash(Json.write(Map.of("finding",finding.toString(),"verdict",challenge.verdict(),"evidence",refs.stream().map(UUID::toString).sorted().toList(),"reason",UnicodeText.strip(challenge.reason()).toLowerCase(Locale.ROOT)))),challenge.verdict(),challenge.reason(),Json.write(refs.stream().map(UUID::toString).toList()),challengeCall);
        }
        Set<String> enabled=new HashSet<>(), custom=new HashSet<>();
        for(Map<String,Object> node:VerificationMaterials.objects(Json.read((String)data.orchestrationJson(id).get("nodes_json"))))if(Boolean.TRUE.equals(node.get("enabled"))) {
            String key=(String)node.get("capabilityKey"); enabled.add(key); if(!VerificationOrchestration.BUILT_IN.contains(key))custom.add(key);
        }
        if(!result.links().isEmpty() && (!enabled.contains("model-link-proposal") || !called(attempt,"LINK_PROPOSAL")))throw stale();
        List<VerificationRules.Link> links=result.links().stream().map(link->new VerificationRules.Link(link.claim(),link.evidence(),link.relation(),link.reason(),0.5,"MODEL",false)).toList();
        List<String> errors=new ArrayList<>(result.nodeErrors());
        for(Map<String,Object> coverage:data.coverage(id))if("UNAVAILABLE".equals(coverage.get("state")) && coverage.get("reason_code") instanceof String code)errors.add(code);
        for(String code:jdbc.queryForList("SELECT DISTINCT CASE WHEN event_json::jsonb->'payloadRedacted'->>'stage'='run_custom_agents' THEN 'CUSTOM_AGENT:' ELSE '' END || (event_json::jsonb->'payloadRedacted'->>'errorCode') FROM agent_task_events WHERE attempt_id=? AND event_json::jsonb->>'eventType'='STAGE_FAILED'",String.class,attempt))if(code!=null)errors.add(code);
        errors=errors.stream().distinct().toList();
        VerificationRules.Outcome outcome=VerificationRules.reconcile(scope,claims,new ArrayList<>(evidence.values()),links,errors,enabled.contains("risk-scan"));
        Set<String> linkKeys=new HashSet<>();
        for(VerificationRules.Link link:outcome.links()) { persistLink(link); linkKeys.add(link.claimId()+":"+link.evidenceId()+":"+link.relation()); }
        Set<String> customSeen=new HashSet<>();
        for(VerificationCandidates.Custom candidate:result.customResults()) {
            if(!custom.contains(candidate.key()) || !customSeen.add(candidate.key()) || (!candidate.links().isEmpty() && !called(attempt,"CUSTOM_AGENT")))throw stale();
            for(VerificationCandidates.Link link:candidate.links())if(claimIds.contains(link.claim()) && evidence.containsKey(link.evidence()) && linkKeys.add(link.claim()+":"+link.evidence()+":"+link.relation()))
                persistLink(new VerificationRules.Link(link.claim(),link.evidence(),link.relation(),link.reason(),0.5,"CUSTOM_AGENT","CONTRADICTS".equals(link.relation())));
        }
        for(VerificationRules.Verdict verdict:outcome.verdicts())data.result(UUID.randomUUID(),id,verdict.claimId(),verdict.status(),verdict.reason(),Json.write(verdict.evidenceIds().stream().map(UUID::toString).toList()),verdict.requiresHumanConfirmation());
        for(VerificationRules.Risk risk:outcome.risks())data.risk(UUID.randomUUID(),id,risk.claimId(),risk.evidenceId(),risk.severity(),risk.recommendation());
        for(VerificationCandidates.Coverage coverage:result.coverage()) {
            if("AGENT".equals(coverage.kind()) && !custom.contains(coverage.reference()))throw stale();
            data.insertCoverage(UUID.randomUUID(),id,coverage.kind(),coverage.reference(),coverage.state(),coverage.reason(),Json.write(coverage.details()));
        }
        summarize(id,result.coverage());
        data.insertCoverage(UUID.randomUUID(),id,"RECONCILIATION","formal-snapshot","ANALYZED",null,Json.write(Map.of("rejectedFindingCount",rejectedFindings,"rejectedChallengeCount",rejectedChallenges,"rejectedLinkCount",outcome.rejectedModelLinks(),"ruleVersion",VerificationRules.VERSION)));
        data.degradation(id,Json.write(Map.of("nodeErrors",errors))); String status=errors.isEmpty()?"SUCCEEDED":"PARTIALLY_COMPLETED";
        data.status(id,status);
        String cycleStatus=outcome.verdicts().isEmpty() || outcome.verdicts().stream().allMatch(item->Set.of("NOT_PROVEN","NOT_ANALYZED").contains(item.status()))?"NEEDS_EVIDENCE":"DRAFT_READY";
        if(outcome.verdicts().stream().anyMatch(VerificationRules.Verdict::requiresHumanConfirmation))cycleStatus="NEEDS_CONFIRMATION";
        data.cycle(cycle,id,cycleStatus);
        data.event(UUID.randomUUID(),id,"reconcile","NODE","SUCCEEDED",id.toString(),Json.write(Map.of("ruleVersion",VerificationRules.VERSION,"resultCount",outcome.verdicts().size())));
        data.event(UUID.randomUUID(),id,null,"JOB_EXECUTION",status,id.toString(),Json.write(Map.of("attempt",task.get("attempt_no"))));
        if(enabled.contains("report-draft")) {
            owners.requireJavaReports(); jdbc.update("INSERT INTO report_generation_jobs(run_id) VALUES(?) ON CONFLICT(run_id) DO NOTHING",id);
            data.event(UUID.randomUUID(),id,"report-draft","REPORT_DRAFT","QUEUED",id.toString(),Json.write(Map.of("automatic",true)));
        }
    }
    private boolean called(UUID attempt,String operation) { return jdbc.queryForObject("SELECT count(*) FROM model_calls WHERE agent_task_attempt_id=? AND operation=? AND status='SUCCEEDED'",Integer.class,attempt,operation)>0; }
    private void summarize(UUID run,List<VerificationCandidates.Coverage> records) {
        VerificationCandidates.Coverage review=records.stream().filter(item->"CODE_REVIEW".equals(item.kind())).findFirst().orElse(null), challenge=records.stream().filter(item->"FINDING_CHALLENGE".equals(item.kind())).findFirst().orElse(null);
        Map<String,Object> capture=data.coverage(run).stream().filter(item->"GIT_CAPTURE".equals(item.get("scope_kind"))).map(item->Json.object((String)item.get("details_json"))).findFirst().orElse(Map.of());
        Map<String,Object> counts=new LinkedHashMap<>();
        for(String verdict:List.of("SUPPORTED","UNSUPPORTED","NEEDS_HUMAN"))counts.put(verdict,jdbc.queryForObject("SELECT count(*) FROM code_review_finding_challenges WHERE analysis_run_id=? AND verdict=?",Integer.class,run,verdict));
        List<String> reasons=new ArrayList<>(); if(review!=null && review.reason()!=null)reasons.add(review.reason()); if(challenge!=null && challenge.reason()!=null)reasons.add(challenge.reason());
        Map<String,Object> details=new LinkedHashMap<>(); details.put("totalFiles",capture.get("totalFiles")); details.put("binaryFiles",capture.get("binaryFiles")); details.put("totalHunks",capture.get("hunkCount"));
        details.put("reviewedHunks",review==null?null:review.details().get("analysedHunks")); details.put("findingCount",jdbc.queryForObject("SELECT count(*) FROM code_review_findings WHERE analysis_run_id=?",Integer.class,run));
        details.put("challengeVerdicts",counts); details.put("uncoveredReasonCodes",reasons);
        boolean complete=review!=null && "ANALYZED".equals(review.state()) && challenge!=null && Set.of("ANALYZED","NOT_APPLICABLE").contains(challenge.state());
        data.insertCoverage(UUID.randomUUID(),run,"STANDARD_VERIFICATION","delivery-git-diff",complete?"ANALYZED":"PARTIAL",reasons.isEmpty()?null:reasons.getFirst(),Json.write(details));
    }
    private void persistLink(VerificationRules.Link link) { data.link(UUID.randomUUID(),link.claimId(),link.evidenceId(),link.relation(),link.reason(),link.confidence(),link.producer(),link.requiresHumanConfirmation()); }
    private Set<UUID> references(VerificationCandidates value) {
        Set<UUID> ids=new HashSet<>(); value.findings().forEach(item->ids.add(item.evidence())); value.challenges().forEach(item->ids.addAll(item.evidence()));
        value.links().forEach(item->ids.add(item.evidence())); value.customResults().forEach(item->item.links().forEach(link->ids.add(link.evidence()))); return ids;
    }
    private ApiProblem citation() { return new ApiProblem(422,"CITATION_INVALID","候选引用超出冻结输入或与引用清单不一致"); }
    private ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","核验结果不属于当前有效执行或冻结配置"); }
}
