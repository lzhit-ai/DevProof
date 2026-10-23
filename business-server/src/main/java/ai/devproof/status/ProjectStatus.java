package ai.devproof.status;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** Frozen projections of recorded facts; no model or delivery-state transitions. */
@Service
public class ProjectStatus {
    private static final Map<String,String> PERIODS=Map.of("DAILY","日报","WEEKLY","周报","ITERATION","迭代总结");
    private final ProjectStatusStore data;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    public ProjectStatus(ProjectStatusStore data,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit) { this.data=data;this.access=access;this.owners=owners;this.commands=commands;this.audit=audit; }
    @Transactional(isolation=Isolation.REPEATABLE_READ) public CommandStore.Result createHealth(UUID project,UUID actor,String milestone,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","SUBMITTER"); owners.requireJavaProjectStatus();
        String normalized=milestone==null?null:UnicodeText.strip(milestone); if("".equals(normalized))normalized=null;
        String selectedMilestone=normalized;
        return commands.execute(command,201,()->{
            var items=data.items(project).stream().filter(row->selectedMilestone==null || selectedMilestone.equals(row.get("milestone_key"))).toList();
            Set<Object> selected=new HashSet<>(); items.forEach(row->selected.add(row.get("id")));
            var active=items.stream().filter(row->!"CANCELLED".equals(row.get("planning_status"))).toList();
            var planning=counts(items,"planning_status");var verification=counts(items,"verification_status");
            long unverified=active.stream().filter(row->"DECLARED_DONE".equals(row.get("planning_status")) && !"CONFIRMED".equals(row.get("verification_status"))).count();
            var links=data.links(project).stream().filter(row->selected.contains(row.get("id"))).toList();
            var activity=data.activity(project);var unattributed=map("taskCount",number(activity.get("task_count")),"gitSnapshotCount",number(activity.get("git_count")));
            var freshness=map("latestSuccessfulSync",sync(data.successfulSync(project),false),"latestSyncAttempt",sync(data.attemptedSync(project),true),"latestItemSourceUpdatedAt",iso(data.lastUpdate(project)));
            var risks=data.risks(project);var riskCounts=counts(risks,"severity");
            var summary=map("plannedItemCount",active.size(),"cancelledItemCount",items.size()-active.size(),"planningStatusCounts",planning,"verificationStatusCounts",verification,
                "declaredDoneButNotVerifiedCount",unverified,"formalRecordItemCount",flagCount(links,"formal_record"),"confirmedChangeLinkedItemCount",flagCount(links,"confirmed_change"),
                "documentSourceLinkedItemCount",flagCount(links,"document_source"),"unattributedActivity",unattributed,"observedRiskCounts",riskCounts,"sourceFreshness",freshness);
            List<String> gaps=new ArrayList<>();if(active.isEmpty())gaps.add("NO_ACTIVE_PLAN_BASELINE");if(freshness.get("latestSuccessfulSync")==null)gaps.add("SOURCE_NOT_SYNCED");if(number(activity.get("git_count"))>0)gaps.add("UNATTRIBUTED_GIT_ACTIVITY");
            var coverage=map("planBaselineAvailable",!active.isEmpty(),"completionRate",null,"verificationCoverage",active.isEmpty()?null:map("numerator",active.stream().filter(row->"CONFIRMED".equals(row.get("verification_status"))).count(),"denominator",active.size()),"dataGaps",gaps,
                "observabilityLimits",List.of("未关联研发事项的 Git 范围只计为待归属开发活动。","历史风险为已记录发现，不等同于当前未关闭风险。","项目态势不以提交数量、PR 数量或外部关闭状态推断完成。"));
            var scope=map("milestoneKey",selectedMilestone,"assessmentProfile","PROJECT_STATUS_SUMMARY");
            var input=map("scope",scope,"items",items.stream().map(ProjectStatus::item).toList(),"risks",risks.stream().map(ProjectStatus::risk).toList(),"summary",summary,"coverage",coverage);
            Instant at=data.now();String hash=Json.hash(Json.canonical(input)),snapshotHash=Json.hash(Json.canonical(map("inputHash",hash,"asOf",iso(at))));UUID id=UUID.randomUUID();
            data.createHealth(id,project,actor,scope,input,hash,snapshotHash,summary,coverage,at);
            audit.append(project,actor,"ProjectHealthSnapshot",id,"PROJECT_HEALTH_SNAPSHOT_CREATED",command.correlationId(),map("snapshotHash",snapshotHash,"scope",scope,"dataGaps",gaps),null,null);
            return ProjectStatusStore.healthView(data.health(project,id));
        });
    }
    @Transactional public List<Map<String,Object>> healthList(UUID project,UUID actor) { access.require(project,actor);return data.healthList(project).stream().map(ProjectStatusStore::healthView).toList(); }
    @Transactional public Map<String,Object> health(UUID project,UUID id,UUID actor) { access.require(project,actor);return ProjectStatusStore.healthView(data.health(project,id)); }
    @Transactional public CommandStore.Result createDraft(UUID project,UUID actor,UUID snapshot,String period,String title,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","SUBMITTER");owners.requireJavaProjectStatus();if(!PERIODS.containsKey(period))throw ApiInput.invalid();
        return commands.execute(command,201,()->{
            var health=data.health(project,snapshot);var content=draftContent(health,period);
            String normalized=title==null?"":UnicodeText.strip(title);if(normalized.isEmpty())normalized=PERIODS.get(period)+"项目态势总结（截至 "+iso(health.get("as_of")).substring(0,10)+"）";
            String hash=Json.hash(Json.canonical(map("title",normalized,"content",content)));UUID id=UUID.randomUUID();
            data.createDraft(id,project,snapshot,period,normalized,content,hash,actor);
            audit.append(project,actor,"ProjectSummaryDraft",id,"PROJECT_SUMMARY_DRAFT_CREATED",command.correlationId(),map("healthSnapshotId",snapshot.toString(),"periodType",period,"contentHash",hash),null,null);
            return ProjectStatusStore.draftView(data.draft(project,id));
        });
    }
    @Transactional public List<Map<String,Object>> drafts(UUID project,UUID actor) { access.require(project,actor);return data.draftList(project).stream().map(ProjectStatusStore::draftView).toList(); }
    @Transactional public CommandStore.Result publish(UUID project,UUID id,UUID actor,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","SUBMITTER");owners.requireJavaProjectStatus();
        return commands.execute(command,201,()->{
            var draft=data.draft(project,id);var existing=data.record(project,id);if(existing!=null)return ProjectStatusStore.recordView(existing);
            if(!"DRAFT".equals(draft.get("draft_status")))throw new ApiProblem(409,"STATE_CONFLICT","项目总结草稿不能发布");
            UUID snapshot=(UUID)draft.get("health_snapshot_id");var health=data.health(project,snapshot);
            String contentHash=Json.hash(Json.canonical(map("title",draft.get("title"),"content",ProjectStatusStore.json(draft,"content_json"))));
            if(!contentHash.equals(draft.get("content_hash")))throw new ApiProblem(409,"INPUT_STALE","项目总结内容与固定摘要不一致");
            String hash=Json.hash(Json.canonical(map("summaryDraftId",id.toString(),"contentHash",contentHash,"healthSnapshotHash",health.get("snapshot_hash"),"confirmationType","PERSONAL_CONFIRMED")));
            UUID record=UUID.randomUUID();String number="PS-"+id.toString().replace("-","").substring(0,16).toUpperCase(Locale.ROOT);
            data.publish(record,project,snapshot,id,number,hash,actor);
            audit.append(project,actor,"ProjectSummaryRecord",record,"PROJECT_SUMMARY_PERSONALLY_CONFIRMED",command.correlationId(),map("draftId",id.toString(),"healthSnapshotId",snapshot.toString(),"recordHash",hash),null,null);
            return ProjectStatusStore.recordView(data.record(project,id));
        });
    }
    @Transactional public List<Map<String,Object>> records(UUID project,UUID actor) { access.require(project,actor);return data.recordList(project).stream().map(ProjectStatusStore::recordView).toList(); }
    private static Map<String,Object> draftContent(Map<String,Object> health,String period) {
        var summary=ProjectStatusStore.json(health,"summary_json");var coverage=ProjectStatusStore.json(health,"coverage_json");
        var planning=object(summary.get("planningStatusCounts"));var verification=object(summary.get("verificationStatusCounts"));var activity=object(summary.get("unattributedActivity"));var risks=object(summary.get("observedRiskCounts"));
        List<String> facts=List.of("纳入态势口径的未取消事项："+summary.get("plannedItemCount")+"；外部已声明完成："+planning.getOrDefault("DECLARED_DONE",0)+"；本系统核验已确认："+verification.getOrDefault("CONFIRMED",0)+"。三项口径彼此独立。",
            "已有正式交付记录覆盖事项："+summary.get("formalRecordItemCount")+"；已确认 PR/Git 变更归属的事项："+summary.get("confirmedChangeLinkedItemCount")+"；已关联验收/设计/计划资料的事项："+summary.get("documentSourceLinkedItemCount")+"。");
        List<String> attention=new ArrayList<>();
        if(number(summary.get("declaredDoneButNotVerifiedCount"))>0)attention.add("外部已声明完成但尚未核验确认的事项："+summary.get("declaredDoneButNotVerifiedCount")+"。");
        if(number(activity.get("gitSnapshotCount"))>0)attention.add("待归属开发活动："+activity.get("gitSnapshotCount")+" 个冻结 Git 范围，来自 "+activity.get("taskCount")+" 个未关联事项的核验任务。");
        if(!risks.isEmpty()) {
            var ordered=new TreeMap<>(risks);var parts=new ArrayList<String>();ordered.forEach((key,value)->parts.add(key+" "+value));
            attention.add("历史交付核验中记录的风险发现："+String.join("，",parts)+"；其是否仍未关闭需要安全基线或人工状态确认。");
        }
        if(attention.isEmpty())attention.add("当前快照没有新增的待归属开发活动或已声明完成但未核验确认事项。");
        return map("kind","PROJECT_STATUS_SUMMARY","periodType",period,"periodLabel",PERIODS.get(period),"healthSnapshotId",health.get("id").toString(),"healthSnapshotHash",health.get("snapshot_hash"),"asOf",iso(health.get("as_of")),
            "scope",ProjectStatusStore.json(health,"scope_json"),"facts",facts,"attention",attention,"dataGaps",coverage.get("dataGaps"),"boundary","本草稿描述已记录事实、数据缺口与待确认项；不将提交、PR 或外部关闭状态写成已完成结论。");
    }
    private static Map<String,Object> item(Map<String,Object> row) { return map("id",row.get("id").toString(),"externalKey",row.get("external_key"),"title",row.get("title"),"planningStatus",row.get("planning_status"),"verificationStatus",row.get("verification_status"),"milestoneKey",row.get("milestone_key"),"sourceUpdatedAt",iso(row.get("source_updated_at")),"externalRevision",row.get("revision_no"),"externalContentHash",row.get("external_content_hash"),"externalWebUrl",row.get("web_url")); }
    private static Map<String,Object> risk(Map<String,Object> row) { return map("riskFindingId",row.get("id").toString(),"analysisRunId",row.get("analysis_run_id").toString(),"severity",row.get("severity"),"category",row.get("category"),"findingKind",row.get("finding_kind")); }
    private static Map<String,Object> sync(Map<String,Object> row,boolean attempt) { if(row==null)return null;var result=map("id",row.get("id").toString(),"status",row.get("status"),"finishedAt",iso(row.get("finished_at")));if(attempt)result.put("errorCode",row.get("error_code"));return result; }
    private static Map<String,Long> counts(List<Map<String,Object>> rows,String field) { Map<String,Long> counts=new TreeMap<>();rows.forEach(row->counts.merge((String)row.get(field),1L,Long::sum));return counts; }
    private static long flagCount(List<Map<String,Object>> rows,String field) { return rows.stream().filter(row->Boolean.TRUE.equals(row.get(field))).count(); }
    private static long number(Object value) { return ((Number)value).longValue(); }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object value) { return (Map<String,Object>)value; }
    private static Map<String,Object> map(Object... entries) { Map<String,Object> result=new LinkedHashMap<>();for(int i=0;i<entries.length;i+=2)result.put((String)entries[i],entries[i+1]);return result; }
    /** Python-compatible UTC representation is retained in new hashes and historical summary drafts. */
    static String iso(Object value) {
        return UtcTime.iso(value);
    }
}
