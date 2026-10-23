package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class VerificationMaterials {
    private final VerificationExecutionMapper data;
    private final InputSnapshotMapper inputs;
    private final ControlledArtifacts artifacts;
    private final long limit;
    public record Capture(Map<String,Object> git,Map<String,Object> bundle) {}
    public VerificationMaterials(VerificationExecutionMapper data,InputSnapshotMapper inputs,ControlledArtifacts artifacts,@Value("${devproof.snapshot-git-max-bytes:33554432}") long limit) {
        this.data=data; this.inputs=inputs; this.artifacts=artifacts; this.limit=limit;
    }
    public Capture capture(UUID snapshot,UUID project) {
        Map<String,Object> git=data.git(snapshot);
        if(git==null || git.get("diff_artifact_id")==null || git.get("code_change_artifact_id")==null)throw new ApiProblem(409,"GIT_ARTIFACT_MISSING","冻结 Git 输入缺少可回放制品");
        Map<String,Object> diff=data.artifact((UUID)git.get("diff_artifact_id"),project), bundle=data.artifact((UUID)git.get("code_change_artifact_id"),project);
        if(diff==null || bundle==null || !"GIT_DIFF".equals(diff.get("kind")) || !"CODE_CHANGE_BUNDLE".equals(bundle.get("kind")))throw new ApiProblem(409,"GIT_ARTIFACT_MISSING","Git 制品不存在或不属于项目");
        if(!Objects.equals(diff.get("content_hash"),git.get("diff_hash")))throw new ApiProblem(409,"GIT_ARTIFACT_HASH_MISMATCH","Git Diff 摘要不一致");
        try {
            artifacts.read((String)diff.get("storage_uri"),limit,(String)diff.get("content_hash"));
            return new Capture(git,Json.object(artifacts.text((String)bundle.get("storage_uri"),limit,(String)bundle.get("content_hash"))));
        } catch(ApiProblem e) { throw new ApiProblem(409,e.code.equals("ARTIFACT_HASH_MISMATCH")?"GIT_ARTIFACT_HASH_MISMATCH":"GIT_ARTIFACT_UNAVAILABLE",e.getMessage()); }
        catch(tools.jackson.core.JacksonException | IllegalArgumentException e) { throw new ApiProblem(409,"GIT_ARTIFACT_UNAVAILABLE","冻结代码制品 JSON 无效"); }
    }
    public void prepare(UUID run,Map<String,Object> snapshot) {
        UUID snapshotId=(UUID)snapshot.get("id"), project=(UUID)snapshot.get("project_id");
        for(Map<String,Object> claim:data.frozenClaims(snapshotId))data.claim(UUID.randomUUID(),run,(String)claim.get("claim_key"),(String)claim.get("text"));
        try {
            Capture capture=capture(snapshotId,project); int count=0;
            for(Map<String,Object> file:objects(capture.bundle().get("files")))for(Map<String,Object> hunk:objects(file.get("hunks"))) {
                String path=Objects.toString(file.get("path"),""), header=Objects.toString(hunk.get("header"),""), payload=Objects.toString(hunk.get("payload"),"");
                UUID existing=data.hunkEvidence(snapshotId,(String)capture.git().get("target_sha"),capture.git().get("diff_artifact_id").toString(),path,header);
                if(existing==null) {
                    String hash=Json.hash(Json.write(Map.of("schemaVersion","git-hunk-v3","artifactId",capture.git().get("diff_artifact_id").toString(),"path",path,"header",header,"payload",payload)));
                    Map<String,Object> locator=new LinkedHashMap<>(); locator.put("artifactId",capture.git().get("diff_artifact_id").toString()); locator.put("commitSha",capture.git().get("target_sha"));
                    locator.put("path",path); locator.put("oldPath",file.get("old_path")); locator.put("hunk",header);
                    locator.put("oldLineStart",hunk.get("old_start")); locator.put("oldLineEnd",hunk.get("old_end")); locator.put("newLineStart",hunk.get("new_start")); locator.put("newLineEnd",hunk.get("new_end"));
                    inputs.evidence(UUID.randomUUID(),project,snapshotId,"CODE","GIT_DIFF_HUNK",null,(String)capture.git().get("target_sha"),hash,SafeExcerpt.text(payload,1600),Json.write(locator),"git-diff-v3",false);
                }
                count++;
            }
            Map<String,Object> details=new LinkedHashMap<>(); details.put("capture",Json.read((String)capture.git().get("coverage_json"))); details.put("bundle",capture.bundle().getOrDefault("coverage",Map.of()));
            details.put("diffArtifactId",capture.git().get("diff_artifact_id").toString()); details.put("codeChangeArtifactId",capture.git().get("code_change_artifact_id").toString()); details.put("hunkCount",count);
            List<Map<String,Object>> files=objects(capture.bundle().get("files")); details.put("totalFiles",files.size()); details.put("binaryFiles",files.stream().filter(file->Boolean.TRUE.equals(file.get("binary"))).count());
            data.insertCoverage(UUID.randomUUID(),run,"GIT_CAPTURE","formal-snapshot",count>0?"ANALYZED":"PARTIAL",count>0?null:"NO_TEXT_HUNKS",Json.write(details));
        } catch(ApiProblem e) {
            data.insertCoverage(UUID.randomUUID(),run,"GIT_CAPTURE","formal-snapshot","UNAVAILABLE",e.code,Json.write(Map.of()));
        }
    }
    public Map<String,Object> read(UUID runId) {
        Map<String,Object> run=data.run(runId); if(run==null)throw new ApiProblem(404,"RESOURCE_NOT_FOUND","运行不存在");
        UUID snapshot=(UUID)run.get("snapshot_id"); List<Map<String,Object>> claims=new ArrayList<>(), evidence=new ArrayList<>();
        for(Map<String,Object> row:data.claims(runId)) {
            Map<String,Object> claim=new LinkedHashMap<>(); claim.put("id",row.get("id").toString()); claim.put("key",row.get("claim_key")); claim.put("text",row.get("text"));
            if(row.get("manifest_json")!=null) { Object acceptance=Json.object((String)row.get("manifest_json")).get("planAcceptance"); if(acceptance!=null)claim.put("planAcceptance",acceptance); }
            claims.add(claim);
        }
        for(Map<String,Object> row:data.evidence(snapshot))evidence.add(Map.of("id",row.get("id").toString(),"sourceType",row.get("source_type"),"kind",row.get("evidence_kind"),
            "precision",row.get("locator_precision"),"excerpt",SafeExcerpt.text((String)row.get("excerpt_safe"),1600),"locator",Json.object((String)row.get("locator_json"))));
        Map<String,Object> orchestration=data.orchestrationJson(runId);
        String raw=OrchestrationBodies.raw(orchestration); Map<String,Object> configuration=Json.object(raw);
        Map<String,Object> output=new LinkedHashMap<>(); output.put("claims",claims); output.put("evidence",evidence);
        output.put("orchestration",configuration); output.put("orchestrationHash",orchestration.get("content_hash"));
        output.put("orchestrationRawJson",raw); output.put("captureCoverage",data.coverage(runId).stream().filter(row->"GIT_CAPTURE".equals(row.get("scope_kind"))).toList());
        try { output.put("bundle",capture(snapshot,(UUID)run.get("project_id")).bundle()); }
        catch(ApiProblem e) { output.put("bundle",null); output.put("captureError",e.code); }
        return output;
    }
    @SuppressWarnings("unchecked") static List<Map<String,Object>> objects(Object value) {
        if(!(value instanceof List<?> list) || list.stream().anyMatch(item->!(item instanceof Map<?,?>)))throw new ApiProblem(409,"GIT_ARTIFACT_UNAVAILABLE","冻结代码制品结构无效");
        return (List<Map<String,Object>>)list;
    }
}
