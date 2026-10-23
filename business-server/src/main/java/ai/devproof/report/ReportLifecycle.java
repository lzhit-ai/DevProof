package ai.devproof.report;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.verification.HumanDecisionPolicy;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReportLifecycle {
    private static final String PROFILE="DELIVERY_VERIFICATION";
    private final ReportWriteMapper data;
    private final ReportMapper reads;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    public ReportLifecycle(ReportWriteMapper data,ReportMapper reads,ProjectAccess access,BusinessOwnership owners,CommandStore commands) {
        this.data=data; this.reads=reads; this.access=access; this.owners=owners; this.commands=commands;
    }
    @Transactional
    public CommandStore.Result create(UUID cycleId,UUID runId,UUID actor,CommandStore.Context command) {
        Map<String,Object> run=runScope(runId,actor);
        if(!cycleId.equals(run.get("cycle_id")))throw stale("运行不属于当前轮次");
        return commands.execute(command,201,()-> {
            data.lockCycle(cycleId); return response(draft(require(data.run(runId)),actor,command.correlationId()));
        });
    }
    @Transactional(propagation=Propagation.NESTED)
    public UUID createAutomatic(UUID runId) {
        owners.requireJavaReports(); Map<String,Object> run=require(data.run(runId));
        UUID actor=(UUID)run.get("created_by"); access.require((UUID)run.get("project_id"),actor,"SUBMITTER","ADMIN");
        data.lockCycle((UUID)run.get("cycle_id")); run=require(data.run(runId));
        UUID existing=data.firstReport(runId); if(existing!=null)return existing;
        return (UUID)draft(run,actor,runId.toString()).get("id");
    }
    private Map<String,Object> draft(Map<String,Object> run,UUID actor,String correlation) {
        open(run); formalRun(run);
        if(!Set.of("SUCCEEDED","PARTIALLY_COMPLETED").contains(run.get("run_status")))throw state("仅终态分析运行可生成报告草稿");
        UUID runId=(UUID)run.get("id"), cycleId=(UUID)run.get("cycle_id"), id=UUID.randomUUID();
        List<Map<String,Object>> results=data.results(runId);
        Map<UUID,Map<String,Object>> decisions=decisions(runId);
        List<Map<String,Object>> hashResults=new ArrayList<>();
        for(Map<String,Object> result:results) hashResults.add(hashResult(result,decisions.get((UUID)result.get("id"))));
        data.draft(id,cycleId,data.nextSequence(cycleId),null,ReportCanonical.hash(hashResults,"",Map.of()),(String)run.get("snapshot_hash"),runId,"");
        int order=0;
        for(Map<String,Object> result:results) {
            UUID resultId=(UUID)result.get("id");
            List<String> allowed=new ArrayList<>();
            for(Object reference:(List<?>)Json.read((String)result.get("evidence_json"))) {
                UUID evidenceId=evidenceId(reference);
                Map<String,Object> evidence=data.evidence(evidenceId);
                if(evidence!=null && run.get("snapshot_id").equals(evidence.get("snapshot_id"))
                    && run.get("project_id").equals(evidence.get("project_id")) && formalEvidence(evidence))allowed.add(evidenceId.toString());
            }
            data.item(UUID.randomUUID(),id,resultId,++order,Json.write(ReportCanonical.result(result,decisions.get(resultId))),
                Json.write(Map.of("evidenceIds",allowed)),null);
        }
        audit(run,actor,"ReportVersion",id,"REPORT_DRAFT_CREATED",correlation,Map.of("runId",runId.toString()));
        return require(data.report(id));
    }
    @Transactional
    public CommandStore.Result edit(UUID id,UUID actor,CommandStore.Context command,int expected,String note,Map<UUID,String> dispositions) {
        Map<String,Object> scope=reportScope(id,actor,"SUBMITTER","ADMIN");
        return commands.execute(command,200,()-> {
            Map<String,Object> report=locked(scope); status(report,"DRAFT");
            if(((Number)report.get("version")).intValue()!=expected)throw new ApiProblem(409,"VERSION_CONFLICT","报告草稿已被其他操作更新，请重新读取");
            List<Map<String,Object>> items=data.items(id); Set<UUID> ids=new HashSet<>();
            for(Map<String,Object> item:items)ids.add((UUID)item.get("id"));
            if(!ids.containsAll(dispositions.keySet()))throw new ApiProblem(422,"INPUT_INVALID","处置项不属于当前报告版本");
            dispositions.forEach(data::disposition);
            data.edit(id,contentHash(report,data.items(id),note),note);
            audit(report,actor,"ReportVersion",id,"REPORT_DRAFT_UPDATED",command.correlationId(),Map.of("version",expected+1));
            return response(data.report(id));
        });
    }
    @Transactional
    public CommandStore.Result submit(UUID id,UUID actor,CommandStore.Context command) {
        Map<String,Object> scope=reportScope(id,actor,"SUBMITTER","ADMIN");
        return commands.execute(command,200,()-> {
            Map<String,Object> report=locked(scope); status(report,"DRAFT"); UUID runId=(UUID)report.get("run_id");
            Map<UUID,Map<String,Object>> decisions=decisions(runId);
            for(Map<String,Object> result:data.results(runId))
                if(Boolean.TRUE.equals(result.get("requires_human_confirmation")) && !decisions.containsKey(result.get("id")))
                    throw new ApiProblem(409,"HUMAN_DECISIONS_REQUIRED","仍有待人工确认的交付结论，请逐项完成裁决");
            data.submit(id,actor); data.cycleStatus((UUID)report.get("cycle_id"),"PENDING_REVIEW");
            audit(report,actor,"ReportVersion",id,"REPORT_SUBMITTED",command.correlationId(),Map.of()); return response(data.report(id));
        });
    }
    @Transactional
    public CommandStore.Result review(UUID id,UUID actor,CommandStore.Context command,String action,String reason) {
        Map<String,Object> scope=reportScope(id,actor,"REVIEWER","ADMIN");
        return commands.execute(command,200,()-> {
            Map<String,Object> report=locked(scope); status(report,"SUBMITTED");
            if(actor.equals(report.get("submitted_by")))throw new ApiProblem(403,"AUTH_FORBIDDEN","提交者不能审批自己的报告");
            data.approval(UUID.randomUUID(),id,action,actor,reason,(String)report.get("content_hash"),(String)report.get("snapshot_hash"),(UUID)report.get("run_id"));
            data.status(id,action);
            UUID cycleId=(UUID)report.get("cycle_id"), resultingId=id;
            if("CHANGES_REQUESTED".equals(action)) {
                resultingId=UUID.randomUUID();
                data.draft(resultingId,cycleId,data.nextSequence(cycleId),id,(String)report.get("content_hash"),
                    (String)report.get("snapshot_hash"),(UUID)report.get("run_id"),(String)report.get("editorial_note"));
                for(Map<String,Object> item:data.items(id))data.item(UUID.randomUUID(),resultingId,(UUID)item.get("result_id"),
                    ((Number)item.get("display_order")).intValue(),(String)item.get("result_json"),(String)item.get("citation_json"),(String)item.get("disposition"));
                data.cycleStatus(cycleId,ReportCanonical.cycleStatus(data.results((UUID)report.get("run_id"))));
            } else data.cycleStatus(cycleId,action);
            String event=switch(action) { case "APPROVED"->"REPORT_APPROVED"; case "REJECTED"->"REPORT_REJECTED"; case "CHANGES_REQUESTED"->"REPORT_CHANGES_REQUESTED"; default->throw state("审批操作无效"); };
            audit(report,actor,"ReportVersion",id,event,command.correlationId(),"CHANGES_REQUESTED".equals(action)?Map.of("newDraftId",resultingId.toString()):Map.of());
            return response(data.report(resultingId));
        });
    }
    @Transactional
    public CommandStore.Result publish(UUID id,UUID actor,CommandStore.Context command) {
        Map<String,Object> scope=reportScope(id,actor,"ADMIN");
        return commands.execute(command,201,()-> {
            Map<String,Object> report=locked(scope); status(report,"APPROVED");
            if(!PROFILE.equals(report.get("record_type")) || !PROFILE.equals(report.get("run_profile")) || !PROFILE.equals(report.get("snapshot_profile")))
                throw new ApiProblem(409,"ASSESSMENT_PROFILE_NOT_ENABLED","当前仅交付核验支持正式记录");
            if(!report.get("snapshot_hash").equals(report.get("actual_snapshot_hash")) || !"FORMAL".equals(report.get("purpose")))throw stale("报告绑定的正式输入快照摘要不一致");
            if(data.matchingApproval(id,(String)report.get("content_hash"),(String)report.get("snapshot_hash"),(UUID)report.get("run_id"))==0)
                throw state("批准记录未绑定当前报告哈希、快照哈希和运行");
            List<Map<String,Object>> items=data.items(id);
            for(Map<String,Object> item:items) for(Object reference:citations(item)) {
                Map<String,Object> evidence=data.evidence(evidenceId(reference));
                if(evidence==null || !report.get("project_id").equals(evidence.get("project_id")) || !report.get("snapshot_id").equals(evidence.get("snapshot_id"))
                    || !formalEvidence(evidence) || !Set.of("EXACT","APPROXIMATE","UNAVAILABLE").contains(evidence.get("locator_precision")))
                    throw new ApiProblem(409,"CITATION_INVALID","证据不存在、定位器无效或不属于当前冻结范围");
            }
            String hash=ReportCanonical.hash(List.of(Map.of("reportContentHash",report.get("content_hash"),"snapshotHash",report.get("snapshot_hash"))),"published-record-v1",Map.of());
            String number=report.get("requirement_key")+"-"+report.get("cycle_sequence")+"-"+report.get("sequence_no");
            Map<String,Object> body=new LinkedHashMap<>();
            body.put("schemaVersion","published-report-body-v1"); body.put("reportVersionId",id.toString());
            body.put("reportContentHash",report.get("content_hash")); body.put("snapshotHash",report.get("snapshot_hash"));
            body.put("recordType",report.get("record_type")); body.put("editorialNote",report.get("editorial_note"));
            body.put("items",Json.read(reads.contentItems(id)));
            Map<String,Object> baseline=reads.planBaseline(id);
            if(baseline!=null) {
                String raw=(String)baseline.get("body_json"); if(!Json.hash(raw).equals(baseline.get("selection_hash")))throw stale("冻结计划摘要不一致");
                body.put("schemaVersion","published-report-body-v2");
                body.put("planBaseline",Map.of("selectionId",baseline.get("selection_id"),"selectionHash",baseline.get("selection_hash"),
                    "planVersionId",baseline.get("plan_version_id"),"planContentHash",baseline.get("plan_content_hash"),"body",Json.object(raw)));
            }
            String encoded=Json.write(body); data.body(id,(String)body.get("schemaVersion"),Json.hash(encoded),encoded);
            UUID recordId=UUID.randomUUID();
            data.publish(recordId,(UUID)report.get("task_id"),(UUID)report.get("cycle_id"),id,number,hash,actor);
            data.status(id,"PUBLISHED"); data.cycleStatus((UUID)report.get("cycle_id"),"PUBLISHED");
            if(report.get("delivery_item_id") instanceof UUID delivery) {
                String deliveryStatus=ReportCanonical.deliveryStatus(items);
                if(data.deliveryStatus(delivery,(UUID)report.get("project_id"),deliveryStatus)==1)
                    audit(report,actor,"DeliveryItem",delivery,"DELIVERY_ITEM_VERIFICATION_STATUS_UPDATED",command.correlationId(),Map.of("verificationStatus",deliveryStatus,"publishedRecordId",recordId.toString()));
            }
            audit(report,actor,"PublishedRecord",recordId,"REPORT_PUBLISHED",command.correlationId(),Map.of());
            return Map.of("id",recordId.toString(),"recordType",PROFILE,"recordNo",number,"recordHash",hash);
        });
    }
    @Transactional
    public CommandStore.Result decide(UUID runId,UUID resultId,UUID actor,CommandStore.Context command,String decision,String note) {
        Map<String,Object> run=runScope(runId,actor);
        return commands.execute(command,200,()-> {
            data.lockCycle((UUID)run.get("cycle_id")); Map<String,Object> current=require(data.run(runId));
            if(!Set.of("SUCCEEDED","PARTIALLY_COMPLETED").contains(current.get("run_status"))
                || Set.of("PUBLISHED","PENDING_REVIEW","APPROVED").contains(current.get("business_status")))throw state("当前运行或审核状态不允许修改人工裁决");
            Map<String,Object> result=data.results(runId).stream().filter(item->resultId.equals(item.get("id"))).findFirst()
                .orElseThrow(()->new ApiProblem(404,"RESOURCE_NOT_FOUND","核验结论不属于当前运行"));
            if(!HumanDecisionPolicy.permits((String)result.get("status"),decision))throw new ApiProblem(422,"INPUT_INVALID","该系统结论不允许采用此人工裁决");
            String clean=UnicodeText.strip(note); if("RETURN_FOR_EVIDENCE".equals(decision) && clean.isEmpty())throw new ApiProblem(422,"INPUT_INVALID","退回补证时必须说明需要补充的内容");
            Map<String,Object> previous=decisions(runId).get(resultId); UUID id=UUID.randomUUID();
            data.decision(id,resultId,decision,clean,actor,previous==null?null:UUID.fromString((String)previous.get("id")));
            refreshDecisions(runId);
            audit(current,actor,"HumanVerificationDecision",id,"HUMAN_VERIFICATION_DECIDED",command.correlationId(),Map.of("runId",runId.toString(),"resultId",resultId.toString(),"decision",decision));
            return ReportCanonical.decision(data.decisionById(id));
        });
    }
    private void refreshDecisions(UUID runId) {
        Map<UUID,Map<String,Object>> decisions=decisions(runId), results=new HashMap<>();
        for(Map<String,Object> result:data.results(runId))results.put((UUID)result.get("id"),result);
        for(UUID id:data.drafts(runId)) {
            for(Map<String,Object> item:data.items(id)) {
                UUID resultId=(UUID)item.get("result_id"); Map<String,Object> result=results.get(resultId);
                if(result!=null)data.itemResult((UUID)item.get("id"),Json.write(ReportCanonical.result(result,decisions.get(resultId))));
            }
            Map<String,Object> report=data.report(id); String note=(String)report.get("editorial_note");
            data.edit(id,contentHash(report,data.items(id),note),note);
        }
    }
    private String contentHash(Map<String,Object> report,List<Map<String,Object>> items,String note) {
        Map<UUID,Map<String,Object>> results=new HashMap<>();
        for(Map<String,Object> result:data.results((UUID)report.get("run_id")))results.put((UUID)result.get("id"),result);
        List<Map<String,Object>> payload=new ArrayList<>(); Map<String,Object> dispositions=new LinkedHashMap<>();
        for(Map<String,Object> item:items) {
            Map<String,Object> frozen=Json.object((String)item.get("result_json"));
            @SuppressWarnings("unchecked") Map<String,Object> decision=(Map<String,Object>)frozen.get("humanDecision");
            payload.add(hashResult(require(results.get(item.get("result_id"))),decision));
            dispositions.put(item.get("id").toString(),item.get("disposition"));
        }
        return ReportCanonical.hash(payload,note,dispositions);
    }
    private Map<String,Object> hashResult(Map<String,Object> result,Map<String,Object> decision) {
        Map<String,Object> payload=new LinkedHashMap<>(); payload.put("id",result.get("id").toString()); payload.put("status",result.get("status"));
        payload.put("evidence",Json.read((String)result.get("evidence_json"))); payload.put("humanDecision",decision); return payload;
    }
    private Map<UUID,Map<String,Object>> decisions(UUID id) {
        Map<UUID,Map<String,Object>> result=new HashMap<>();
        for(Map<String,Object> row:data.decisions(id))result.put((UUID)row.get("result_id"),ReportCanonical.decision(row)); return result;
    }
    private Map<String,Object> runScope(UUID id,UUID actor) {
        owners.requireJavaReports(); Map<String,Object> run=require(data.run(id));
        access.require((UUID)run.get("project_id"),actor,"SUBMITTER","ADMIN"); return run;
    }
    private Map<String,Object> reportScope(UUID id,UUID actor,String... roles) {
        owners.requireJavaReports(); Map<String,Object> report=require(data.report(id));
        access.require((UUID)report.get("project_id"),actor,roles); return report;
    }
    private Map<String,Object> locked(Map<String,Object> scope) {
        data.lockCycle((UUID)scope.get("cycle_id")); Map<String,Object> report=require(data.report((UUID)scope.get("id"))); open(report); return report;
    }
    private void open(Map<String,Object> scope) { if("PUBLISHED".equals(scope.get("business_status")))throw state("核验轮次已发布，历史报告版本不可修改"); }
    private void status(Map<String,Object> report,String expected) { if(!expected.equals(report.get("status")))throw state("报告当前状态不允许执行此操作"); }
    private void formalRun(Map<String,Object> run) {
        if(!PROFILE.equals(run.get("assessment_profile")) || !PROFILE.equals(run.get("snapshot_profile")))throw new ApiProblem(409,"ASSESSMENT_PROFILE_NOT_ENABLED","当前仅交付核验支持报告草稿");
        if(!"FORMAL".equals(run.get("purpose")))throw stale("报告草稿必须绑定正式输入快照");
    }
    private boolean formalEvidence(Map<String,Object> evidence) { return !"TOOL".equals(evidence.get("source_type")) && !"HTTP_QUERY".equals(evidence.get("evidence_kind")); }
    private UUID evidenceId(Object value) {
        try { return UUID.fromString(value.toString()); } catch(IllegalArgumentException e) { throw new ApiProblem(409,"CITATION_INVALID","引用不是合法 Evidence ID"); }
    }
    private List<?> citations(Map<String,Object> item) { return (List<?>)Json.object((String)item.get("citation_json")).getOrDefault("evidenceIds",List.of()); }
    private Map<String,Object> require(Map<String,Object> value) { if(value==null)throw new ApiProblem(404,"RESOURCE_NOT_FOUND","报告或核验运行不存在"); return value; }
    private Map<String,Object> response(Map<String,Object> report) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(String key:List.of("id","cycle_id","sequence_no","status","record_type","content_hash","editorial_note","version"))result.put(key,report.get(key)); return result;
    }
    private void audit(Map<String,Object> scope,UUID actor,String type,UUID id,String action,String correlation,Map<String,Object> payload) {
        data.audit(UUID.randomUUID(),(UUID)scope.get("project_id"),actor,type,id,action,correlation,Json.write(payload));
    }
    private ApiProblem state(String message) { return new ApiProblem(409,"STATE_CONFLICT",message); }
    private ApiProblem stale(String message) { return new ApiProblem(409,"INPUT_STALE",message); }
}
