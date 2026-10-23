package ai.devproof.planning;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import ai.devproof.infrastructure.UnicodeText;
import ai.devproof.project.ProjectAccess;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Owns plan selections; claim and formal snapshot writes remain with their current owner. */
@Service
public class PlanBindingService {
    private final PlanBindingMapper data;
    private final PlanningMapper plans;
    private final ProjectAccess access;
    public PlanBindingService(PlanBindingMapper data,PlanningMapper plans,ProjectAccess access) {
        this.data=data; this.plans=plans; this.access=access;
    }
    public record Binding(String issueKey,String acceptanceKey,UUID claimId) {}
    private record CriterionKey(String issueKey,String acceptanceKey) {}

    public List<Map<String,Object>> options(UUID projectId,UUID actorId) {
        access.require(projectId,actorId); return data.options(projectId);
    }
    public Map<String,Object> plan(UUID projectId,UUID planId,UUID actorId) {
        access.require(projectId,actorId); return project(requirePlan(projectId,planId));
    }
    public Map<String,Object> get(UUID projectId,UUID cycleId,UUID actorId) {
        access.require(projectId,actorId); require(data.cycle(projectId,cycleId));
        return state(cycleId);
    }
    private Map<String,Object> state(UUID cycleId) {
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("selection",project(data.current(cycleId)));
        result.put("frozen",data.frozen(cycleId));
        result.put("history",data.history(cycleId).stream().map(this::project).toList());
        return result;
    }
    @Transactional
    public Map<String,Object> bind(UUID projectId,UUID cycleId,UUID actorId,UUID planId,String expectedHash,UUID expectedSelectionId,List<Binding> bindings) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN");
        editable(require(data.lockCycle(projectId,cycleId)),cycleId);
        Map<String,Object> plan=requirePlan(projectId,planId);
        if(!expectedHash.equals(plan.get("content_hash")))throw conflict("所选计划内容摘要已变化，请重新读取");
        Map<String,Object> body=Json.object((String)plan.get("body_json"));
        Map<CriterionKey,Map<String,Object>> criteria=criteria(body);
        Set<CriterionKey> seen=new HashSet<>(); Set<UUID> claimIds=new HashSet<>();
        List<Map<String,Object>> mappings=new ArrayList<>();
        for(Binding binding:bindings) {
            CriterionKey key=new CriterionKey(binding.issueKey(),binding.acceptanceKey());
            Map<String,Object> criterion=criteria.get(key);
            if(criterion==null || !seen.add(key) || !claimIds.add(binding.claimId()))
                throw new ApiProblem(422,"PLAN_BINDING_INVALID","验收项不存在或存在重复绑定");
            Map<String,Object> claim=data.claim(cycleId,binding.claimId());
            if(claim==null || !"CONFIRMED".equals(claim.get("claim_status")))throw conflict("请先确认本轮实际交付主张");
            String condition=UnicodeText.strip((String)criterion.get("condition"));
            if(!condition.equals(UnicodeText.strip((String)claim.get("text"))))throw conflict("计划验收条件与交付主张不一致，请重新应用所选验收项");
            mappings.add(Map.of("issueKey",binding.issueKey(),"acceptanceKey",binding.acceptanceKey(),
                "claimId",binding.claimId().toString(),"claimKey",claim.get("claim_key"),
                "claimTextHash",Json.hash((String)claim.get("text")),"criterion",criterion));
        }
        mappings.sort(Comparator.<Map<String,Object>,String>comparing(item->(String)item.get("issueKey"))
            .thenComparing(item->(String)item.get("acceptanceKey")));
        Map<String,Object> frozen=Map.of("schemaVersion","cycle-plan-selection-v1","cycleId",cycleId.toString(),
            "planVersionId",planId.toString(),"planContentHash",expectedHash,"ideaId",plan.get("idea_id").toString(),
            "ideaRevisionNo",plan.get("idea_revision_no"),"planSequenceNo",plan.get("sequence_no"),
            "planningRepositoryId",plan.get("repository_id").toString(),"planningTargetSha",plan.get("target_sha"),"mappings",mappings);
        String encoded=Json.write(frozen), hash=Json.hash(encoded);
        Map<String,Object> current=data.current(cycleId);
        if(current!=null && hash.equals(current.get("content_hash")))return state(cycleId);
        if(!Objects.equals(expectedSelectionId,current==null?null:current.get("id")))throw conflict("本轮计划关联已被其他操作修改，请重新读取");
        UUID id=UUID.randomUUID();
        data.selection(id,cycleId,planId,data.nextSequence(cycleId),expectedHash,hash,encoded,actorId);
        data.select(cycleId,id); return state(cycleId);
    }
    @Transactional
    public Map<String,Object> clear(UUID projectId,UUID cycleId,UUID actorId,UUID expectedSelectionId) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN");
        editable(require(data.lockCycle(projectId,cycleId)),cycleId);
        Map<String,Object> current=data.current(cycleId);
        if(current!=null && !Objects.equals(expectedSelectionId,current.get("id")))throw conflict("本轮计划关联已变化，请重新读取后再清除");
        data.clear(cycleId); return state(cycleId);
    }
    public Map<String,Object> trace(UUID projectId,UUID cycleId,UUID actorId) {
        access.require(projectId,actorId); require(data.cycle(projectId,cycleId));
        List<Map<String,Object>> runs=new ArrayList<>();
        for(Map<String,Object> run:data.runs(cycleId)) {
            Map<String,Object> item=new LinkedHashMap<>(run);
            UUID id=(UUID)run.get("run_id");
            List<Map<String,Object>> results=new ArrayList<>();
            if(id!=null) for(Map<String,Object> row:data.results(id)) {
                Map<String,Object> result=new LinkedHashMap<>(row);
                Object evidence=result.remove("evidence_ids_json");
                result.put("evidenceIds",evidence==null?List.of():Json.read(evidence.toString())); results.add(result);
            }
            item.put("results",results); item.put("reports",id==null?List.of():data.reports(id)); runs.add(item);
        }
        return Map.of("selections",data.history(cycleId).stream().map(this::project).toList(),"runs",runs);
    }
    private void editable(Map<String,Object> cycle,UUID cycleId) {
        if(!Set.of("DRAFT","NEEDS_EVIDENCE","NEEDS_CONFIRMATION").contains(cycle.get("business_status")) || data.frozen(cycleId))
            throw conflict("本轮正式输入已固定；请创建新轮次后选择其他计划基线");
    }
    /** Caller holds the verification cycle lock; this reads the selected immutable baseline. */
    public Map<String,Object> forSnapshot(UUID projectId,UUID cycleId,UUID repositoryId,List<Map<String,Object>> claims) {
        Map<String,Object> selection=data.current(cycleId);
        if(selection==null)return null;
        String raw=(String)selection.get("body_json");
        if(!Json.hash(raw).equals(selection.get("content_hash")))throw conflict("计划选择摘要不一致");
        UUID planId=(UUID)selection.get("plan_version_id"); Map<String,Object> plan=requirePlan(projectId,planId), body=Json.object(raw);
        if(!Objects.equals(body.get("cycleId"),cycleId.toString()) || !Objects.equals(body.get("planVersionId"),planId.toString())
            || !Objects.equals(body.get("planContentHash"),selection.get("plan_content_hash")) || !Objects.equals(plan.get("content_hash"),selection.get("plan_content_hash"))
            || !Objects.equals(body.get("planningRepositoryId"),plan.get("repository_id").toString()) || !Objects.equals(body.get("planningTargetSha"),plan.get("target_sha")))
            throw conflict("计划选择引用与已确认内容不一致");
        if(!repositoryId.equals(plan.get("repository_id"))) {
            Map<String,Object> planned=plans.repository(projectId,(UUID)plan.get("repository_id")), actual=plans.repository(projectId,repositoryId);
            String plannedKey=repositoryIdentity(planned), actualKey=repositoryIdentity(actual);
            if(plannedKey==null || !plannedKey.equals(actualKey))throw conflict("开发代码与所选计划必须来自同一仓库");
        }
        Map<CriterionKey,Map<String,Object>> expected=criteria(Json.object((String)plan.get("body_json")));
        Map<String,Map<String,Object>> byId=new HashMap<>();
        for(Map<String,Object> claim:claims)byId.put(claim.get("id").toString(),claim);
        List<Map<String,Object>> mappings=PlanValidator.objects(body,"mappings",12);
        if(mappings.isEmpty())throw conflict("计划选择缺少实际验收绑定");
        Set<CriterionKey> seen=new HashSet<>(); Set<String> claimIds=new HashSet<>();
        for(Map<String,Object> mapping:mappings) {
            CriterionKey key=new CriterionKey((String)mapping.get("issueKey"),(String)mapping.get("acceptanceKey"));
            Map<String,Object> criterion=expected.get(key), claim=byId.get(mapping.get("claimId"));
            if(!seen.add(key) || !claimIds.add((String)mapping.get("claimId")) || claim==null || criterion==null
                || !criterion.equals(mapping.get("criterion")) || !Objects.equals(mapping.get("claimKey"),claim.get("claim_key"))
                || !Objects.equals(mapping.get("claimTextHash"),Json.hash((String)claim.get("text")))
                || !UnicodeText.strip((String)claim.get("text")).equals(UnicodeText.strip((String)criterion.get("condition"))))
                throw conflict("交付主张已变化，请重新应用所选计划验收项");
        }
        return Map.of("selectionId",selection.get("id").toString(),"selectionHash",selection.get("content_hash"),
            "planVersionId",planId.toString(),"planContentHash",plan.get("content_hash"),"body",body);
    }
    private String repositoryIdentity(Map<String,Object> repository) {
        if(repository==null)return null;
        try {
            java.net.URI uri=java.net.URI.create((String)repository.get("display_url"));
            if((!"https".equals(uri.getScheme()) && !"ssh".equals(uri.getScheme())) || !"github.com".equalsIgnoreCase(uri.getHost()))return null;
            String path=uri.getPath().replaceAll("^/+|/+$","").replaceAll("\\.git$","");
            return path.split("/").length==2?path.toLowerCase(Locale.ROOT):null;
        } catch(IllegalArgumentException e) { return null; }
    }
    private Map<String,Object> requirePlan(UUID projectId,UUID id) {
        Map<String,Object> plan=require(plans.planContext(id));
        if(!projectId.equals(plan.get("project_id")))throw new ApiProblem(404,"RESOURCE_NOT_FOUND","计划不属于当前项目");
        if(!Set.of("CONFIRMED","SUPERSEDED").contains(plan.get("status")) || plan.get("confirmed_at")==null)
            throw conflict("只能绑定经人工确认的计划版本");
        if(!Json.hash((String)plan.get("body_json")).equals(plan.get("content_hash")))
            throw conflict("计划正文与内容摘要不一致");
        return plan;
    }
    @SuppressWarnings("unchecked")
    private Map<CriterionKey,Map<String,Object>> criteria(Map<String,Object> body) {
        Map<CriterionKey,Map<String,Object>> result=new HashMap<>();
        for(Map<String,Object> issue:(List<Map<String,Object>>)body.get("issues"))
            for(Map<String,Object> criterion:(List<Map<String,Object>>)issue.get("acceptanceCriteria"))
                result.put(new CriterionKey((String)issue.get("key"),(String)criterion.get("key")),criterion);
        return result;
    }
    private Map<String,Object> project(Map<String,Object> row) {
        if(row==null)return null;
        Map<String,Object> result=new LinkedHashMap<>(row); Object body=result.remove("body_json");
        if(body!=null)result.put("body",Json.object(body.toString())); return result;
    }
    private Map<String,Object> require(Map<String,Object> row) {
        if(row==null)throw new ApiProblem(404,"RESOURCE_NOT_FOUND","计划或核验轮次不存在"); return row;
    }
    private ApiProblem conflict(String message) { return new ApiProblem(409,"PLAN_BASELINE_CONFLICT",message); }
}
