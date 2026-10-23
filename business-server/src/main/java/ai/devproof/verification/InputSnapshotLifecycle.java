package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import ai.devproof.planning.PlanBindingService;
import ai.devproof.project.ProjectAccess;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Freezes business facts and materializes evidence. It never invokes a model. */
@Service
public class InputSnapshotLifecycle {
    private static final String SCHEMA="verification-input-v2";
    private final InputSnapshotMapper data;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final ControlledArtifacts artifacts;
    private final PlanBindingService plans;
    private final long textLimit,gitLimit;
    public InputSnapshotLifecycle(InputSnapshotMapper data,ProjectAccess access,BusinessOwnership owners,CommandStore commands,
            ControlledArtifacts artifacts,PlanBindingService plans,
            @Value("${devproof.snapshot-text-max-bytes:8388608}") long textLimit,
            @Value("${devproof.snapshot-git-max-bytes:33554432}") long gitLimit) {
        this.data=data; this.access=access; this.owners=owners; this.commands=commands; this.artifacts=artifacts; this.plans=plans;
        if(textLimit<4096 || textLimit>536870912 || gitLimit<4096 || gitLimit>536870912)throw new IllegalArgumentException("Invalid snapshot artifact budgets");
        this.textLimit=textLimit; this.gitLimit=gitLimit;
    }
    public record Selection(List<UUID> sourceIds,UUID gitId,List<UUID> externalIds,List<UUID> manualIds) {}
    private record Document(Map<String,Object> source,List<Map<String,Object>> chunks) {}

    @Transactional
    public CommandStore.Result preparation(UUID cycleId,UUID actor,CommandStore.Context command,List<UUID> sourceIds) {
        Map<String,Object> scope=scope(cycleId,actor);
        return commands.execute(command,201,()-> {
            Map<String,Object> cycle=locked(cycleId); if(!"DRAFT".equals(cycle.get("business_status")))throw state("只有草稿轮次可冻结准备输入");
            if(sourceIds.isEmpty())throw invalid("至少选择一份资料版本");
            List<Document> documents=documents((UUID)scope.get("project_id"),sourceIds,true);
            Map<String,Object> body=base(cycleId,"PREPARATION"); body.put("sources",documentRefs(documents));
            UUID snapshot=save(cycle,actor,body);
            if(snapshot==null)return response(data.byHash(Json.hash(Json.write(body))));
            materializeDocuments((UUID)scope.get("project_id"),snapshot,documents);
            audit(cycle,actor,snapshot,"PREPARATION_SNAPSHOT_FROZEN",command,Map.of("sourceRevisionIds",sourceIds.stream().map(UUID::toString).toList()));
            return response(data.snapshot(snapshot));
        });
    }
    @Transactional
    public CommandStore.Result formal(UUID cycleId,UUID actor,CommandStore.Context command,Selection selection) {
        Map<String,Object> scope=scope(cycleId,actor);
        return commands.execute(command,201,()-> {
            Map<String,Object> cycle=locked(cycleId); UUID project=(UUID)scope.get("project_id");
            if(!Set.of("DRAFT","NEEDS_EVIDENCE","NEEDS_CONFIRMATION").contains(cycle.get("business_status")))throw state("当前轮次不能冻结新的正式输入");
            Map<String,Object> git=require(data.git(selection.gitId(),cycleId));
            UUID repositoryId=(UUID)git.get("repository_id"); require(data.repository(project,repositoryId));
            Map<String,Object> diff=artifact(project,(UUID)git.get("diff_artifact_id"),"GIT_DIFF"), bundle=artifact(project,(UUID)git.get("code_change_artifact_id"),"CODE_CHANGE_BUNDLE");
            if(!Objects.equals(git.get("diff_hash"),diff.get("content_hash")))throw stale("Git 范围与 Diff 制品摘要不一致");
            artifacts.read((String)diff.get("storage_uri"),gitLimit,(String)diff.get("content_hash"));
            String bundleText=artifacts.text((String)bundle.get("storage_uri"),gitLimit,(String)bundle.get("content_hash"));
            if(!(Json.read(bundleText) instanceof Map<?,?>))throw stale("冻结代码变更制品不是合法对象");
            List<Map<String,Object>> claims=data.claims(cycleId);
            if(claims.isEmpty())throw new ApiProblem(409,"CLAIMS_NOT_CONFIRMED","请先确认本次交付主张");
            Map<String,Object> requirement=require(data.requirement((UUID)cycle.get("delivery_item_id")));
            if(!"PULL_REQUEST".equals(requirement.get("resource_type")))throw invalid("正式快照只能绑定本项目已同步的 Pull Request");
            if(!project.equals(requirement.get("delivery_project_id")) || !Objects.equals(requirement.get("resource_id"),requirement.get("external_resource_id")))
                throw stale("Pull Request 修订与本项目交付项不一致");
            List<Document> documents=documents(project,selection.sourceIds(),false);
            Set<String> selectedSources=new HashSet<>(); documents.forEach(document->selectedSources.add(document.source().get("id").toString()));
            for(Map<String,Object> claim:claims) {
                Map<String,Object> manifest=Json.object((String)claim.get("manifest_json"));
                Object raw=manifest.getOrDefault("documents",List.of());
                if(!(raw instanceof List<?> entries))throw stale("交付主张来源清单无效");
                for(Object entry:entries)if(entry instanceof Map<?,?> ref && ref.get("sourceRevisionId")!=null && !selectedSources.contains(ref.get("sourceRevisionId").toString()))
                    throw stale("交付主张引用的资料版本未纳入本次正式输入");
            }
            Map<String,Object> baseline=plans.forSnapshot(project,cycleId,repositoryId,claims);
            List<Map<String,Object>> external=external(project,cycleId,selection.externalIds(),(String)git.get("target_sha"));
            List<Map<String,Object>> manual=manual(project,cycleId,selection.manualIds());
            List<Map<String,Object>> claimRefs=claimRefs(claims,baseline);
            String requirementText=UnicodeText.strip(requirement.get("title")+"\n\n"+requirement.get("body"));
            String requirementExcerpt=SafeExcerpt.text(requirementText,1000);
            Map<String,Object> requirementRef=fields(requirement,"id","content_hash","title","body","web_url");
            requirementRef.put("excerptSafe",requirementExcerpt);
            Map<String,Object> body=base(cycleId,"FORMAL");
            body.put("requirement",requirementRef);
            body.put("deliveryItemId",cycle.get("delivery_item_id").toString()); body.put("deliveryClaims",claimRefs);
            body.put("git",fields(git,"id","repository_id","base_sha","target_sha","merge_base_sha","effective_base_sha","diff_mode","diff_hash","diff_artifact_id","code_change_artifact_id"));
            body.put("codeChangeArtifactHash",bundle.get("content_hash")); body.put("sources",documentRefs(documents));
            body.put("externalEvidence",external.stream().map(row->{Map<String,Object> ref=fields(row,"id","content_hash","commit_sha","evidence_type","logical_name","exit_code"); ref.put("excerptSafe",row.get("excerpt")); return ref;}).toList());
            body.put("manualEvidence",manual.stream().map(row->{Map<String,Object> ref=fields(row,"id","content_hash","submitted_by","logical_name","origin_type"); ref.put("origin",Json.object((String)row.get("origin_json"))); ref.put("excerptSafe",row.get("excerpt")); return ref;}).toList());
            if(baseline!=null) { Map<String,Object> ref=new LinkedHashMap<>(baseline); ref.remove("body"); body.put("planBaseline",ref); }
            UUID snapshot=save(cycle,actor,body);
            if(snapshot==null)return response(data.byHash(Json.hash(Json.write(body))));
            if(baseline!=null)data.plan(snapshot,UUID.fromString((String)baseline.get("selectionId")),UUID.fromString((String)baseline.get("planVersionId")),(String)baseline.get("planContentHash"),(String)baseline.get("selectionHash"));
            for(Map<String,Object> claim:claimRefs)data.claim(UUID.randomUUID(),snapshot,UUID.fromString((String)claim.get("id")),(String)claim.get("key"),
                (String)claim.get("text"),(String)claim.get("origin"),Json.write(claim.get("sourceManifest")),(String)claim.get("contentHash"));
            data.gitBinding(UUID.randomUUID(),snapshot,selection.gitId(),(String)git.get("diff_hash"));
            data.evidence(UUID.randomUUID(),project,snapshot,"PULL_REQUEST","RAW_FACT",null,null,(String)requirement.get("content_hash"),requirementExcerpt,
                Json.write(Map.of("deliveryItemId",cycle.get("delivery_item_id").toString(),"externalResourceRevisionId",requirement.get("id").toString(),"webUrl",requirement.get("web_url"))),"github-pr-v1",false);
            materializeDocuments(project,snapshot,documents);
            for(Map<String,Object> row:external) {
                UUID id=(UUID)row.get("id"); String hash=(String)row.get("content_hash"), sha=(String)row.get("commit_sha");
                data.externalBinding(UUID.randomUUID(),snapshot,id,hash,sha);
                Map<String,Object> locator=fields(row,"exit_code"); locator.put("externalEvidenceId",id.toString()); locator.put("logicalName",row.get("logical_name"));
                locator.put("commitSha",sha); locator.put("exitCode",locator.remove("exit_code"));
                data.evidence(UUID.randomUUID(),project,snapshot,(String)row.get("evidence_type"),"RAW_FACT",null,sha,hash,(String)row.get("excerpt"),Json.write(locator),"external-evidence-v1",false);
            }
            for(Map<String,Object> row:manual) {
                UUID id=(UUID)row.get("id"); String hash=(String)row.get("content_hash");
                data.manualBinding(UUID.randomUUID(),snapshot,id,hash);
                Map<String,Object> locator=new LinkedHashMap<>(); locator.put("manualEvidenceId",id.toString()); locator.put("logicalName",row.get("logical_name"));
                locator.put("submittedBy",row.get("submitted_by").toString()); locator.put("originType",row.get("origin_type")); locator.put("origin",Json.object((String)row.get("origin_json")));
                data.evidence(UUID.randomUUID(),project,snapshot,"MANUAL","HUMAN_NOTE",null,null,hash,(String)row.get("excerpt"),Json.write(locator),"manual-evidence-v1",true);
            }
            audit(cycle,actor,snapshot,"FORMAL_SNAPSHOT_FROZEN",command,Map.of("gitSnapshotId",selection.gitId().toString(),"deliveryClaimCount",claims.size()));
            return response(data.snapshot(snapshot));
        });
    }
    public Map<String,Object> frozen(UUID snapshotId,UUID actor) {
        Map<String,Object> snapshot=require(data.snapshot(snapshotId)), cycle=require(data.cycle((UUID)snapshot.get("cycle_id")));
        access.require((UUID)cycle.get("project_id"),actor); Map<String,Object> body=data.body(snapshotId);
        if(body==null)throw new ApiProblem(409,"SNAPSHOT_BODY_NOT_MATERIALIZED","该历史版本没有完整输入正文，保留原有冻结绑定与摘要");
        if(!Objects.equals(body.get("content_hash"),snapshot.get("snapshot_hash")) || !Json.hash((String)body.get("body_json")).equals(snapshot.get("snapshot_hash")))throw stale("冻结输入正文摘要不一致");
        return Map.of("snapshotId",snapshotId,"schemaVersion",body.get("schema_version"),"contentHash",body.get("content_hash"),"rawJson",body.get("body_json"));
    }
    private List<Document> documents(UUID project,List<UUID> ids,boolean requireReady) {
        unique(ids); String active=data.activeIndex(project); List<Document> result=new ArrayList<>();
        for(UUID id:ids.stream().sorted(Comparator.comparing(UUID::toString)).toList()) {
            Map<String,Object> source=require(data.source(project,id));
            if(requireReady && !"READY".equals(source.get("processing_status")))throw new ApiProblem(409,"SOURCE_NOT_READY","所选资料尚未完成处理");
            List<Map<String,Object>> all=data.chunks(id), selected=active==null?List.of():all.stream().filter(chunk->active.equals(chunk.get("index_version"))).toList();
            if(selected.isEmpty()) {
                Map<Integer,Map<String,Object>> first=new LinkedHashMap<>();
                for(Map<String,Object> chunk:all)first.putIfAbsent(((Number)chunk.get("chunk_index")).intValue(),chunk);
                selected=List.copyOf(first.values());
            }
            for(Map<String,Object> chunk:selected)if(!Json.hash((String)chunk.get("content")).equals(chunk.get("text_hash")))throw stale("资料分块内容摘要不一致");
            result.add(new Document(source,selected));
        }
        return result;
    }
    private List<Map<String,Object>> documentRefs(List<Document> documents) {
        return documents.stream().map(document->{
            Map<String,Object> ref=fields(document.source(),"id","content_hash","parser_version","processing_status");
            ref.put("chunks",document.chunks().stream().map(chunk->{
                Map<String,Object> copy=fields(chunk,"id","chunk_index","index_version","text_hash");
                copy.put("locator",documentLocator(document.source(),chunk)); copy.put("excerptSafe",SafeExcerpt.text((String)chunk.get("content"),1000));
                copy.put("extractorVersion",Objects.toString(document.source().get("parser_version"),"markdown-text-v1")); return copy;
            }).toList());
            return ref;
        }).toList();
    }
    private void materializeDocuments(UUID project,UUID snapshot,List<Document> documents) {
        for(Document document:documents) {
            Map<String,Object> source=document.source(); UUID sourceId=(UUID)source.get("id");
            data.sourceBinding(UUID.randomUUID(),snapshot,sourceId,(String)source.get("content_hash"),Objects.toString(source.get("parser_version"),"unknown"));
            for(Map<String,Object> chunk:document.chunks())data.evidence(UUID.randomUUID(),project,snapshot,"DOCUMENT","RAW_FACT",sourceId,null,
                (String)chunk.get("text_hash"),SafeExcerpt.text((String)chunk.get("content"),1000),Json.write(documentLocator(source,chunk)),Objects.toString(source.get("parser_version"),"markdown-text-v1"),false);
        }
    }
    private Map<String,Object> documentLocator(Map<String,Object> source,Map<String,Object> chunk) {
        Map<String,Object> locator=new LinkedHashMap<>(Json.object((String)chunk.get("locator_json")));
        locator.put("sourceRevisionId",source.get("id").toString()); locator.put("chunkId",chunk.get("id").toString()); locator.put("chunkIndex",chunk.get("chunk_index")); return locator;
    }
    private List<Map<String,Object>> claimRefs(List<Map<String,Object>> claims,Map<String,Object> baseline) {
        Map<String,Map<String,Object>> planned=new HashMap<>();
        if(baseline!=null) {
            @SuppressWarnings("unchecked") Map<String,Object> body=(Map<String,Object>)baseline.get("body");
            @SuppressWarnings("unchecked") List<Map<String,Object>> mappings=(List<Map<String,Object>>)body.get("mappings");
            for(Map<String,Object> item:mappings)planned.put((String)item.get("claimId"),item);
        }
        List<Map<String,Object>> result=new ArrayList<>();
        for(Map<String,Object> claim:claims) {
            String id=claim.get("id").toString(); Map<String,Object> manifest=new LinkedHashMap<>(Json.object((String)claim.get("manifest_json"))), mapping=planned.get(id);
            if(mapping!=null)manifest.put("planAcceptance",Map.of("planVersionId",baseline.get("planVersionId"),"planContentHash",baseline.get("planContentHash"),"selectionHash",baseline.get("selectionHash"),
                "issueKey",mapping.get("issueKey"),"acceptanceKey",mapping.get("acceptanceKey"),"criterion",mapping.get("criterion")));
            result.add(Map.of("id",id,"key",claim.get("claim_key"),"text",claim.get("text"),"origin",claim.get("origin"),"sourceManifest",manifest,"contentHash",Json.hash((String)claim.get("text"))));
        }
        return result;
    }
    private List<Map<String,Object>> external(UUID project,UUID cycle,List<UUID> ids,String sha) {
        unique(ids); List<Map<String,Object>> result=new ArrayList<>();
        for(UUID id:ids.stream().sorted(Comparator.comparing(UUID::toString)).toList()) {
            Map<String,Object> row=new LinkedHashMap<>(require(data.external(project,cycle,id)));
            if(!sha.equals(row.get("commit_sha")))throw stale("测试与构建证据必须绑定冻结目标提交");
            row.put("excerpt",SafeExcerpt.text(artifacts.text((String)row.get("artifact_uri"),textLimit,(String)row.get("content_hash")),1000)); result.add(row);
        }
        return result;
    }
    private List<Map<String,Object>> manual(UUID project,UUID cycle,List<UUID> ids) {
        unique(ids); List<Map<String,Object>> result=new ArrayList<>();
        for(UUID id:ids.stream().sorted(Comparator.comparing(UUID::toString)).toList()) {
            Map<String,Object> row=new LinkedHashMap<>(require(data.manual(project,cycle,id)));
            row.put("excerpt",SafeExcerpt.text(artifacts.text((String)row.get("artifact_uri"),textLimit,(String)row.get("content_hash")),1000)); result.add(row);
        }
        return result;
    }
    private UUID save(Map<String,Object> cycle,UUID actor,Map<String,Object> body) {
        String raw=Json.write(body), hash=Json.hash(raw); Map<String,Object> existing=data.byHash(hash);
        if(existing!=null)return null;
        UUID id=UUID.randomUUID(); data.create(id,(UUID)cycle.get("id"),hash,actor,(String)body.get("purpose")); data.insertBody(id,hash,raw); return id;
    }
    private Map<String,Object> scope(UUID cycleId,UUID actor) {
        owners.requireJavaInputs(); Map<String,Object> cycle=require(data.cycle(cycleId)); access.require((UUID)cycle.get("project_id"),actor,"SUBMITTER","ADMIN"); return cycle;
    }
    private Map<String,Object> locked(UUID cycleId) { data.lockCycle(cycleId); return require(data.cycle(cycleId)); }
    private Map<String,Object> artifact(UUID project,UUID id,String kind) {
        if(id==null)throw new ApiProblem(409,"GIT_ARTIFACT_MISSING","正式快照必须使用可回放的 Git 制品");
        Map<String,Object> artifact=require(data.artifact(id,project)); if(!kind.equals(artifact.get("kind")))throw stale("冻结 Git 制品类型不一致"); return artifact;
    }
    private Map<String,Object> base(UUID cycle,String purpose) { return new LinkedHashMap<>(Map.of("schemaVersion",SCHEMA,"cycleId",cycle.toString(),"purpose",purpose,"assessmentProfile","DELIVERY_VERIFICATION","policyVersion","v2","workflowVersion","v1")); }
    private Map<String,Object> fields(Map<String,Object> row,String... keys) {
        Map<String,Object> result=new LinkedHashMap<>(); for(String key:keys) { Object value=row.get(key); result.put(key,value instanceof UUID?value.toString():value); } return result;
    }
    private void unique(List<UUID> ids) { if(new HashSet<>(ids).size()!=ids.size())throw invalid("输入版本不能重复选择"); }
    private Map<String,Object> response(Map<String,Object> snapshot) {
        Map<String,Object> response=fields(snapshot,"id","cycle_id","snapshot_hash","purpose","assessment_profile","policy_version","workflow_version");
        response.put("created_at",((Timestamp)snapshot.get("created_at")).toInstant().toString()); return response;
    }
    private void audit(Map<String,Object> cycle,UUID actor,UUID id,String event,CommandStore.Context context,Map<String,Object> fields) {
        Map<String,Object> payload=new LinkedHashMap<>(fields); payload.put("snapshotHash",data.snapshot(id).get("snapshot_hash")); payload.put("schemaVersion",SCHEMA);
        data.audit(UUID.randomUUID(),(UUID)cycle.get("project_id"),actor,id,event,context.correlationId(),Json.write(payload));
    }
    private Map<String,Object> require(Map<String,Object> row) { if(row==null)throw new ApiProblem(404,"RESOURCE_NOT_FOUND","输入资源不存在或不属于当前项目/轮次"); return row; }
    private ApiProblem invalid(String message) { return new ApiProblem(422,"INPUT_INVALID",message); }
    private ApiProblem stale(String message) { return new ApiProblem(409,"INPUT_STALE",message); }
    private ApiProblem state(String message) { return new ApiProblem(409,"STATE_CONFLICT",message); }
}
