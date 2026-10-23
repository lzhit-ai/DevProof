package ai.devproof.securitybaseline;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.status.ProjectStatusStore;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import static ai.devproof.securitybaseline.SecurityBaselines.map;

/** Deterministic projections of explicitly selected inputs, independent of delivery verification. */
@Service
public class PeripheralRuns {
    private static final Set<String> PROFILES=Set.of("PROJECT_STATUS_SUMMARY","SECURITY_BASELINE","QUALITY_TREND");
    private record Projection(Map<String,Object> manifest,Map<String,Object> output,Map<String,Object> coverage,List<String> limitations) {}
    private final PeripheralStore data;
    private final SecurityStore security;
    private final ProjectStatusStore health;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    public PeripheralRuns(PeripheralStore data,SecurityStore security,ProjectStatusStore health,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit) { this.data=data;this.security=security;this.health=health;this.access=access;this.owners=owners;this.commands=commands;this.audit=audit; }
    @Transactional(isolation=Isolation.REPEATABLE_READ) public CommandStore.Result create(UUID project,UUID actor,Map<String,Object> body,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","SUBMITTER");owners.requireJavaPeripheralProfiles();
        String profile=ApiInput.text(body,"assessment_profile",1,48);if(!PROFILES.contains(profile))throw ApiInput.invalid();
        UUID healthId=ApiInput.optionalUuid(body,"health_snapshot_id"),baselineId=ApiInput.optionalUuid(body,"security_baseline_id");
        List<UUID> scans=body.get("scan_artifact_ids")==null?null:ApiInput.uuids(body,"scan_artifact_ids",300);
        boolean valid=switch(profile) {
            case "PROJECT_STATUS_SUMMARY" -> healthId!=null && baselineId==null && scans==null;
            case "SECURITY_BASELINE" -> baselineId!=null && healthId==null && scans==null;
            default -> healthId==null && baselineId==null && scans!=null && scans.size()>=2 && new HashSet<>(scans).size()==scans.size();
        };
        if(!valid)throw ApiInput.invalid();
        return commands.execute(command,201,()->{
            Projection projection=switch(profile) {
                case "PROJECT_STATUS_SUMMARY" -> statusProjection(project,healthId);
                case "SECURITY_BASELINE" -> baselineProjection(project,baselineId);
                default -> qualityProjection(project,scans);
            };
            UUID id=UUID.randomUUID();var output=data.create(id,project,profile,projection.manifest(),projection.output(),projection.coverage(),projection.limitations(),actor);
            audit.append(project,actor,"PeripheralProfileRun",id,"PERIPHERAL_PROFILE_RUN_CREATED",command.correlationId(),map("assessmentProfile",profile,"inputHash",output.get("input_hash"),"runStatus","SUCCEEDED"),null,null);return output;
        });
    }
    @Transactional public List<Map<String,Object>> list(UUID project,UUID actor,String profile) { access.require(project,actor);if(profile!=null && !PROFILES.contains(profile))throw ApiInput.invalid();return data.list(project,profile); }
    private Projection statusProjection(UUID project,UUID id) {
        var snapshot=health.health(project,id);var coverage=ProjectStatusStore.json(snapshot,"coverage_json");var limits=limits(coverage,"observabilityLimits");
        limits.add("本次外围运行只复用该态势快照，不读取提交、PR 或仓库代码来补写项目完成结论。");String at=UtcTime.iso(snapshot.get("as_of"));
        var manifest=map("profile","PROJECT_STATUS_SUMMARY","healthSnapshot",map("id",id.toString(),"snapshotHash",snapshot.get("snapshot_hash"),"inputHash",snapshot.get("input_hash"),"asOf",at));
        return new Projection(manifest,map("scope",ProjectStatusStore.json(snapshot,"scope_json"),"summary",ProjectStatusStore.json(snapshot,"summary_json"),"asOf",at),coverage,limits);
    }
    private Projection baselineProjection(UUID project,UUID id) {
        var snapshot=security.baseline(project,id);var coverage=SecurityStore.json(snapshot,"coverage_json");var limits=limits(coverage,"limitations");
        limits.add("本次外围运行只复用该安全基线，不执行扫描器、不读取仓库，也不输出安全通过或发布通过结论。");
        var manifest=map("profile","SECURITY_BASELINE","securityBaseline",map("id",id.toString(),"repositoryId",snapshot.get("repository_id").toString(),"targetSha",snapshot.get("target_sha"),"snapshotHash",snapshot.get("snapshot_hash"),"inputHash",snapshot.get("input_hash")));
        return new Projection(manifest,map("targetSha",snapshot.get("target_sha"),"summary",SecurityStore.json(snapshot,"summary_json"),"coverage",coverage),coverage,limits);
    }
    private Projection qualityProjection(UUID project,List<UUID> ids) {
        var artifacts=ids.stream().map(id->security.artifact(project,id)).sorted(Comparator.<Map<String,Object>,java.time.Instant>comparing(row->((java.sql.Timestamp)row.get("created_at")).toInstant()).thenComparing(row->row.get("id").toString())).toList();
        var key=SecurityBaselines.comparableKey(artifacts.getFirst());
        if(artifacts.stream().anyMatch(row->!key.equals(SecurityBaselines.comparableKey(row))))throw new ApiProblem(422,"INPUT_INVALID","质量趋势只能比较同一仓库、扫描类型、扫描器版本与规则版本的工件");
        var grouped=SecurityBaselines.byArtifact(security.findings(project,ids));
        var points=artifacts.stream().map(row->SecurityBaselines.trendPoint(row,grouped.getOrDefault((UUID)row.get("id"),List.of()),true)).toList();
        var comparable=map("repositoryId",key.get(0),"scanType",key.get(1),"scannerName",key.get(2),"scannerVersion",key.get(3),"ruleSetVersion",key.get(4));
        var manifest=map("profile","QUALITY_TREND","comparability",comparable,"scanArtifacts",points.stream().map(row->map("id",row.get("artifactId"),"targetSha",row.get("targetSha"),"createdAt",row.get("createdAt"),"contentHash",row.get("contentHash"),"findingCount",row.get("findingCount"),"severityCounts",row.get("severityCounts"),"statusCounts",row.get("statusCounts"),"coverage",row.get("coverage"))).toList());
        var coverage=map("pointCount",points.size(),"scannerCoverage",points.stream().map(row->map("artifactId",row.get("artifactId"),"coverage",row.get("coverage"))).toList());
        return new Projection(manifest,map("comparability",comparable,"points",points),coverage,List.of("只比较本次冻结的同一仓库、扫描类型、扫描器名称与版本、规则版本工件。","提交数量、PR 关联、Agent 推断与未导入代码均不参与质量趋势。","发现数的变化只描述这组可比工件的导入结果，不等同于整体项目质量或安全状态。"));
    }
    private static List<String> limits(Map<String,Object> body,String key) {
        Object value=body.getOrDefault(key,List.of());if(!(value instanceof List<?> values) || values.stream().anyMatch(item->!(item instanceof String)))throw new ApiProblem(409,"INPUT_STALE","历史快照的范围说明不符合结构");
        return new ArrayList<>(values.stream().map(String.class::cast).toList());
    }
}
