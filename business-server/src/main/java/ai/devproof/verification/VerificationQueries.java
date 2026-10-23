package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VerificationQueries {
    private final VerificationReadStore data;
    private final ProjectAccess access;
    public VerificationQueries(VerificationReadStore data,ProjectAccess access) { this.data=data; this.access=access; }
    private Map<String,Object> scope(UUID id,UUID actor) {
        var run=data.run(id); if(run==null)throw missing("分析运行不存在");
        access.require((UUID)run.get("project_id"),actor,"SUBMITTER","REVIEWER","ADMIN"); return run;
    }
    @Transactional public Map<String,Object> run(UUID id,UUID actor) { return runView(scope(id,actor)); }
    @Transactional public Map<String,Object> latest(UUID task,UUID actor) {
        var row=data.task(task); if(row==null)throw missing("核验任务不存在");
        access.require((UUID)row.get("project_id"),actor,"SUBMITTER","REVIEWER","ADMIN");
        UUID id=data.latest(task); if(id==null)throw missing("该核验任务尚未创建分析运行"); return runView(scope(id,actor));
    }
    @Transactional public Map<String,Object> events(UUID id,UUID actor,UUID before,int limit) {
        scope(id,actor);
        if(limit<1 || limit>200)throw ApiInput.invalid();
        var rows=data.events(id,before,limit+1);boolean more=rows.size()>limit;
        var page=new ArrayList<>(rows.subList(0,Math.min(limit,rows.size())));Collections.reverse(page);
        Map<String,Object> response=new LinkedHashMap<>();
        response.put("items",page.stream().map(row->{
            Map<String,Object> event=new LinkedHashMap<>(); event.put("id",row.get("id")); event.put("nodeId",row.get("node_id"));
            event.put("eventType",row.get("event_type")); event.put("status",row.get("status"));
            event.put("details",Json.object((String)row.get("payload_json"))); event.put("createdAt",time(row.get("created_at"))); return event;
        }).toList());
        response.put("has_more",more);response.put("next_cursor",more?page.getFirst().get("id"):null);return response;
    }
    @Transactional public List<Map<String,Object>> results(UUID id,UUID actor) {
        var run=scope(id,actor); UUID snapshot=(UUID)run.get("snapshot_id"),project=(UUID)run.get("project_id");
        var savedResults=data.results(id); Map<UUID,List<UUID>> references=new HashMap<>(); Set<UUID> allRefs=new LinkedHashSet<>();
        for(var row:savedResults) { var refs=ids((String)row.get("evidence_json")); references.put((UUID)row.get("id"),refs); allRefs.addAll(refs); }
        Map<UUID,Map<String,Object>> evidence=byId(data.evidence(snapshot,project,allRefs));
        Map<UUID,Map<String,Object>> decisions=new HashMap<>(); for(var row:data.decisions(id))decisions.put((UUID)row.get("result_id"),row);
        var assessments=group(data.assessments(id,snapshot,project,allRefs),"claim_id"); var risks=group(data.risks(id),"claim_id");
        List<Map<String,Object>> results=new ArrayList<>();
        for(var row:savedResults) {
            UUID claim=(UUID)row.get("claim_id"); List<UUID> refs=references.get((UUID)row.get("id")); Set<UUID> allowed=new HashSet<>();
            List<Map<String,Object>> citations=new ArrayList<>();
            for(UUID ref:refs)if(evidence.containsKey(ref) && allowed.add(ref)) {
                var item=evidence.get(ref); citations.add(Map.of("id",ref,"sourceType",item.get("source_type"),"excerpt",item.get("excerpt_safe"),"locator",Json.object((String)item.get("locator_json")),"precision",item.get("locator_precision")));
            }
            Map<String,Object> value=new LinkedHashMap<>();
            for(String key:List.of("id","claim_id","claim_key","claim_text","status","reason","requires_human_confirmation"))value.put(key,row.get(key));
            value.put("human_decision",decision(decisions.get((UUID)row.get("id"))));
            value.put("allowed_human_decisions",HumanDecisionPolicy.options((String)row.get("status")));
            value.put("evidence",citations);
            value.put("evidence_assessments",assessments.getOrDefault(claim,List.of()).stream().filter(link->allowed.contains(link.get("evidence_id"))).map(link->Map.of("evidenceId",link.get("evidence_id"),"relation",link.get("relation"),"reason",link.get("reason"),"producedBy",link.get("produced_by"))).toList());
            value.put("risks",risks.getOrDefault(claim,List.of()).stream().map(risk->Map.of("id",risk.get("id"),"severity",risk.get("severity"),"category",risk.get("category"),"findingKind",risk.get("finding_kind"),"recommendation",risk.get("recommendation"))).toList());
            results.add(value);
        }
        return results;
    }
    @Transactional public Map<String,Object> codeReview(UUID id,UUID actor) {
        var run=scope(id,actor); UUID snapshot=(UUID)run.get("snapshot_id"),project=(UUID)run.get("project_id");
        Map<UUID,Map<String,Object>> challenges=new HashMap<>();
        for(var row:data.challenges(id))challenges.put((UUID)row.get("finding_id"),row);
        var savedFindings=data.findings(id,snapshot,project); Set<UUID> allRefs=new LinkedHashSet<>(); Map<UUID,List<UUID>> challengeRefs=new HashMap<>();
        for(var row:savedFindings) {
            UUID finding=(UUID)row.get("id"); allRefs.add((UUID)row.get("evidence_id")); var challenge=challenges.get(finding);
            var refs=challenge==null?List.<UUID>of():ids((String)challenge.get("evidence_json")); challengeRefs.put(finding,refs); allRefs.addAll(refs);
        }
        var evidence=byId(data.evidence(snapshot,project,allRefs));
        List<Map<String,Object>> findings=new ArrayList<>();
        for(var row:savedFindings) {
            if(!evidence.containsKey(row.get("evidence_id")))throw new ApiProblem(409,"CITATION_INVALID","代码发现引用不属于本运行已冻结证据");
            Map<String,Object> value=new LinkedHashMap<>();
            for(String[] field:List.of(new String[]{"id","id"},new String[]{"claimId","claim_id"},new String[]{"evidenceId","evidence_id"},
                new String[]{"severity","severity"},new String[]{"findingKind","finding_kind"},new String[]{"title","title"},new String[]{"problem","problem"},
                new String[]{"triggerScenario","trigger_scenario"},new String[]{"recommendation","recommendation"},new String[]{"confidence","confidence"},new String[]{"requiresHumanConfirmation","requires_human_confirmation"}))value.put(field[0],row.get(field[1]));
            var saved=challenges.get((UUID)row.get("id")); Map<String,Object> challenge=new LinkedHashMap<>();
            challenge.put("state",saved==null?"NOT_STARTED":"COMPLETED"); challenge.put("verdict",saved==null?null:saved.get("verdict")); challenge.put("reason",saved==null?null:saved.get("reason"));
            var refs=challengeRefs.get((UUID)row.get("id"));
            if(refs.stream().anyMatch(ref->!evidence.containsKey(ref)))throw new ApiProblem(409,"CITATION_INVALID","代码复核引用不属于本运行已冻结证据");
            challenge.put("evidenceIds",refs); value.put("challenge",challenge); findings.add(value);
        }
        var coverage=data.coverage(id).stream().map(row->{
            Map<String,Object> value=new LinkedHashMap<>(); value.put("scopeKind",row.get("scope_kind")); value.put("scopeRef",row.get("scope_ref"));
            value.put("state",row.get("state")); value.put("reasonCode",row.get("reason_code")); value.put("details",Json.object((String)row.get("details_json"))); return value;
        }).toList();
        Map<String,Object> result=new LinkedHashMap<>(); result.put("gitSnapshotId",data.git(snapshot)); result.put("findings",findings); result.put("coverage",coverage); return result;
    }
    private static Map<String,Object> runView(Map<String,Object> run) {
        return Map.of("id",run.get("id"),"snapshot_id",run.get("snapshot_id"),"assessment_profile",run.get("assessment_profile"),"run_status",run.get("run_status"),"poll_url","/api/v1/analysis-runs/"+run.get("id"));
    }
    private static Map<String,Object> decision(Map<String,Object> row) {
        if(row==null)return null;
        Map<String,Object> value=new LinkedHashMap<>(); value.put("id",row.get("id")); value.put("decision",row.get("decision")); value.put("note",row.get("note")); value.put("actorId",row.get("actor_id")); value.put("createdAt",time(row.get("created_at"))); return value;
    }
    private static String time(Object raw) { return raw==null?null:((Timestamp)raw).toInstant().toString(); }
    private static List<UUID> ids(String raw) {
        Object value=Json.read(raw); if(!(value instanceof List<?> list))throw new ApiProblem(409,"CITATION_INVALID","已保存证据引用格式无效");
        try { return list.stream().map(item->UUID.fromString((String)item)).toList(); }
        catch(RuntimeException error) { throw new ApiProblem(409,"CITATION_INVALID","已保存证据引用格式无效"); }
    }
    private static Map<UUID,Map<String,Object>> byId(List<Map<String,Object>> rows) { Map<UUID,Map<String,Object>> result=new LinkedHashMap<>(); for(var row:rows)result.put((UUID)row.get("id"),row); return result; }
    private static Map<UUID,List<Map<String,Object>>> group(List<Map<String,Object>> rows,String key) {
        Map<UUID,List<Map<String,Object>>> result=new HashMap<>(); for(var row:rows)if(row.get(key) instanceof UUID id)result.computeIfAbsent(id,ignored->new ArrayList<>()).add(row); return result;
    }
    private static ApiProblem missing(String message) { return new ApiProblem(404,"RESOURCE_NOT_FOUND",message); }
}
