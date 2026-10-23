package ai.devproof.securitybaseline;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class SecurityBaselines {
    private static final Set<String> SCANS=Set.of("SAST","DEPENDENCY","SECRET","CONFIG","CI");
    private static final Set<String> SEVERITIES=Set.of("INFO","LOW","MEDIUM","HIGH","CRITICAL");
    private static final Set<String> STATUSES=Set.of("OPEN","ACCEPTED_RISK","REMEDIATION_CLAIMED");
    private static final Set<String> RECOMMENDED=Set.of("SAST","DEPENDENCY","SECRET","CONFIG");
    private static final long MAX_SCAN_BYTES=8L*1024*1024;
    private final SecurityStore data;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final JavaArtifacts artifacts;
    private final ControlledArtifacts files;
    public SecurityBaselines(SecurityStore data,ProjectAccess access,BusinessOwnership owners,CommandStore commands,BusinessAudit audit,JavaArtifacts artifacts,ControlledArtifacts files) {
        this.data=data;this.access=access;this.owners=owners;this.commands=commands;this.audit=audit;this.artifacts=artifacts;this.files=files;
    }
    @Transactional public CommandStore.Result importScan(UUID project,UUID actor,Map<String,Object> body,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","SUBMITTER");owners.requireJavaSecurityBaselines();
        UUID repository=ApiInput.uuid(body.get("repository_id"));String sha=sha(body),type=ApiInput.text(body,"scan_type",1,24);
        if(!SCANS.contains(type))throw ApiInput.invalid();
        String scanner=clean(body,"scanner_name",160),version=clean(body,"scanner_version",160),rules=clean(body,"rule_set_version",160);
        var coverage=optionalObject(body,"coverage");String content=ApiInput.text(body,"content",1,2*1024*1024);
        Object supplied=body.getOrDefault("findings",List.of());if(!(supplied instanceof List<?> values) || values.size()>2000)throw ApiInput.invalid();
        List<Map<String,Object>> findings=new ArrayList<>();Set<String> fingerprints=new HashSet<>();
        for(Object value:values) {
            var entry=object(value);String fingerprint=clean(entry,"fingerprint",255),severity=ApiInput.text(entry,"severity",1,16);
            if(!fingerprints.add(fingerprint) || !SEVERITIES.contains(severity))throw ApiInput.invalid();
            findings.add(map("fingerprint",fingerprint,"severity",severity,"category",clean(entry,"category",128),"title",clean(entry,"title",4000),"locator",optionalObject(entry,"locator")));
        }
        data.repository(project,repository);
        return commands.execute(command,201,()->{
            UUID id=UUID.randomUUID();byte[] bytes=content.getBytes(StandardCharsets.UTF_8);
            var saved=artifacts.save(project,"SECURITY_SCAN","security-scan-content-v1","text/plain; charset=utf-8",bytes);
            data.createArtifact(id,project,repository,sha,type,scanner,version,rules,coverage,Json.hash(bytes),(String)saved.get("storage_uri"),actor);
            for(var finding:findings)data.createFinding(UUID.randomUUID(),id,(String)finding.get("fingerprint"),(String)finding.get("severity"),(String)finding.get("category"),(String)finding.get("title"),object(finding.get("locator")));
            audit.append(project,actor,"SecurityScanArtifact",id,"SECURITY_SCAN_ARTIFACT_IMPORTED",command.correlationId(),map("targetSha",sha,"scanType",type,"scanner",scanner,"ruleSetVersion",rules,"contentHash",Json.hash(bytes),"findingCount",findings.size()),null,null);
            return SecurityStore.artifactView(data.artifact(project,id));
        });
    }
    @Transactional public List<Map<String,Object>> scans(UUID project,UUID actor) { access.require(project,actor);return data.artifacts(project).stream().map(SecurityStore::artifactView).toList(); }
    @Transactional public List<Map<String,Object>> findings(UUID project,UUID artifact,UUID actor) {
        access.require(project,actor);data.artifact(project,artifact);
        return data.findings(project,List.of(artifact)).stream().sorted(Comparator.<Map<String,Object>,String>comparing(row->(String)row.get("severity")).reversed().thenComparing(row->(String)row.get("category")).thenComparing(row->row.get("id").toString())).map(SecurityStore::findingView).toList();
    }
    @Transactional public CommandStore.Result status(UUID project,UUID id,UUID actor,String status,String reason,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","REVIEWER");owners.requireJavaSecurityBaselines();if(!STATUSES.contains(status))throw ApiInput.invalid();
        String normalized=UnicodeText.strip(reason);if(normalized.isEmpty())throw ApiInput.invalid();
        return commands.execute(command,200,()->{
            var finding=data.finding(project,id);data.status(id,status,normalized,actor);
            audit.append(project,actor,"SecurityFinding",id,"SECURITY_FINDING_STATUS_UPDATED",command.correlationId(),map("status",status,"reason",normalized,"scanArtifactId",finding.get("scan_artifact_id").toString()),null,null);
            return SecurityStore.findingView(data.finding(project,id));
        });
    }
    @Transactional(isolation=Isolation.REPEATABLE_READ) public Map<String,Object> explain(UUID project,UUID id,UUID actor) {
        access.require(project,actor);var artifact=data.artifact(project,id);var findings=data.findings(project,List.of(id));
        var statuses=counts(findings,"finding_status");long high=findings.stream().filter(row->Set.of("HIGH","CRITICAL").contains(row.get("severity"))).count();
        var observations=new ArrayList<>(List.of("该说明只针对 "+artifact.get("scan_type")+" 工件、目标 SHA "+((String)artifact.get("target_sha")).substring(0,12)+"…、扫描器 "+artifact.get("scanner_name")+" "+artifact.get("scanner_version")+" 与规则 "+artifact.get("rule_set_version")+"。",
            "导入结果包含 "+findings.size()+" 条风险，其中高/严重风险 "+high+" 条。"));
        if(statuses.getOrDefault("REMEDIATION_CLAIMED",0L)>0)observations.add("存在“已声明整改”的风险；该状态仍需要同范围的新扫描结果验证，不能描述为已修复。");
        if(findings.isEmpty())observations.add("该工件没有导入风险；这不等同于项目安全、代码已全部扫描或发布通过。");
        var scope=map("artifactId",id.toString(),"repositoryId",artifact.get("repository_id").toString(),"targetSha",artifact.get("target_sha"),"scanType",artifact.get("scan_type"),"scannerName",artifact.get("scanner_name"),"scannerVersion",artifact.get("scanner_version"),"ruleSetVersion",artifact.get("rule_set_version"),"coverage",SecurityStore.json(artifact,"coverage_json"),"contentHash",artifact.get("content_hash"));
        return map("scope",scope,"summary",map("findingCount",findings.size(),"severityCounts",counts(findings,"severity"),"statusCounts",statuses,"categoryCounts",counts(findings,"category")),"observations",observations,"limitations",List.of(
            "解释只读取这一份已导入扫描工件及其结构化风险，不读取仓库、分支或未导入的扫描输出。","覆盖范围以扫描器声明为准；未纳入的路径、依赖、配置、规则或扫描类型不产生安全结论。","风险处置状态是人工处置事实，不替代后续扫描验证。"));
    }
    @Transactional(isolation=Isolation.REPEATABLE_READ) public Map<String,Object> trend(UUID project,UUID actor) {
        access.require(project,actor);var artifacts=data.trendArtifacts(project);var findings=byArtifact(data.findings(project,ids(artifacts)));
        Map<List<String>,List<Map<String,Object>>> groups=new LinkedHashMap<>();
        for(var artifact:artifacts)groups.computeIfAbsent(comparableKey(artifact),ignored->new ArrayList<>()).add(trendPoint(artifact,findings.getOrDefault((UUID)artifact.get("id"),List.of()),false));
        var series=new ArrayList<Map<String,Object>>();groups.forEach((key,points)->series.add(map("series_key",String.join(":",key),"repository_id",key.get(0),"scan_type",key.get(1),"scanner_name",key.get(2),"scanner_version",key.get(3),"rule_set_version",key.get(4),"points",points)));
        return map("series",series,"limitations",List.of("只比较同一仓库、扫描类型、扫描器、扫描器版本和规则版本的导入结果。","扫描器或规则版本变更会形成新序列，不与旧序列解释为风险上升或下降。","趋势来自导入扫描/CI 工件，不以提交数量、PR 关联、Agent 推断或未导入代码替代质量事实。"));
    }
    @Transactional(isolation=Isolation.REPEATABLE_READ) public CommandStore.Result createBaseline(UUID project,UUID actor,UUID repository,String sha,List<UUID> selected,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","SUBMITTER");owners.requireJavaSecurityBaselines();data.repository(project,repository);
        if(selected.isEmpty() || selected.size()>100 || new HashSet<>(selected).size()!=selected.size())throw ApiInput.invalid();
        return commands.execute(command,201,()->{
            var scans=selected.stream().map(id->data.artifact(project,id)).toList();
            if(scans.stream().anyMatch(row->!repository.equals(row.get("repository_id")) || !sha.equals(row.get("target_sha"))))throw new ApiProblem(422,"INPUT_INVALID","安全基线的所有扫描输入必须绑定同一仓库和目标 SHA");
            for(var scan:scans)files.read((String)scan.get("artifact_uri"),MAX_SCAN_BYTES,(String)scan.get("content_hash"));
            var findings=data.findings(project,selected);var findingManifest=findings.stream().map(row->map("id",row.get("id").toString(),"scanArtifactId",row.get("scan_artifact_id").toString(),"fingerprint",row.get("fingerprint"),"severity",row.get("severity"),"category",row.get("category"),"status",row.get("finding_status"),"locator",SecurityStore.json(row,"locator_json"))).toList();
            var scanManifest=scans.stream().map(row->map("id",row.get("id").toString(),"scanType",row.get("scan_type"),"scannerName",row.get("scanner_name"),"scannerVersion",row.get("scanner_version"),"ruleSetVersion",row.get("rule_set_version"),"coverage",SecurityStore.json(row,"coverage_json"),"contentHash",row.get("content_hash"))).toList();
            var types=new TreeSet<String>();scans.forEach(row->types.add((String)row.get("scan_type")));var missing=new TreeSet<>(RECOMMENDED);missing.removeAll(types);
            var summary=map("findingCount",findings.size(),"severityCounts",counts(findings,"severity"),"statusCounts",counts(findings,"finding_status"),"scanTypeCounts",counts(scans,"scan_type"));
            var coverage=map("providedScanTypes",types,"missingRecommendedScanTypes",missing,"scannerCoverage",scanManifest.stream().map(row->map("scanArtifactId",row.get("id"),"scanType",row.get("scanType"),"coverage",row.get("coverage"))).toList(),"limitations",List.of(
                "该基线只覆盖导入扫描器声明的路径、依赖、配置和规则版本。","未导入扫描输入的范围不产生安全结论。","风险状态为人工处置状态；REMEDIATION_CLAIMED 仍需新的扫描输入验证。"));
            var manifest=map("repositoryId",repository.toString(),"targetSha",sha,"scanArtifacts",scanManifest,"findings",findingManifest);String hash=Json.hash(Json.canonical(manifest));
            var at=data.now();String snapshotHash=Json.hash(Json.canonical(map("inputHash",hash,"createdAt",UtcTime.iso(at).replace("Z","+00:00"))));UUID id=UUID.randomUUID();
            data.createBaseline(id,project,repository,sha,manifest,hash,snapshotHash,summary,coverage,actor,at);
            audit.append(project,actor,"SecurityBaselineSnapshot",id,"SECURITY_BASELINE_CREATED",command.correlationId(),map("targetSha",sha,"snapshotHash",snapshotHash,"scanArtifactCount",scans.size()),null,null);
            return SecurityStore.baselineView(data.baseline(project,id));
        });
    }
    @Transactional public List<Map<String,Object>> baselines(UUID project,UUID actor) { access.require(project,actor);return data.baselines(project).stream().map(SecurityStore::baselineView).toList(); }
    @Transactional public CommandStore.Result confirm(UUID project,UUID id,UUID actor,String reason,CommandStore.Context command) {
        access.require(project,actor,"ADMIN","REVIEWER");owners.requireJavaSecurityBaselines();String normalized=UnicodeText.strip(reason);if(normalized.isEmpty())throw ApiInput.invalid();
        return commands.execute(command,201,()->{
            var baseline=data.baseline(project,id);var existing=data.record(project,id);if(existing!=null)return SecurityStore.recordView(existing);
            String hash=Json.hash(Json.canonical(map("snapshotHash",baseline.get("snapshot_hash"),"reason",normalized,"confirmation","REVIEWER_OR_ADMIN")));UUID record=UUID.randomUUID();String number="SB-"+id.toString().replace("-","").substring(0,16).toUpperCase(Locale.ROOT);
            data.confirm(record,project,id,number,hash,normalized,actor);
            audit.append(project,actor,"SecurityBaselineRecord",record,"SECURITY_BASELINE_CONFIRMED",command.correlationId(),map("baselineId",id.toString(),"recordHash",hash),null,null);
            return SecurityStore.recordView(data.record(project,id));
        });
    }
    @Transactional public List<Map<String,Object>> records(UUID project,UUID actor) { access.require(project,actor);return data.records(project).stream().map(SecurityStore::recordView).toList(); }
    static String sha(Map<String,Object> body) { String value=ApiInput.text(body,"target_sha",40,40);if(!value.matches("[0-9a-fA-F]{40}"))throw ApiInput.invalid();return value.toLowerCase(Locale.ROOT); }
    static List<UUID> ids(List<Map<String,Object>> rows) { return rows.stream().map(row->(UUID)row.get("id")).toList(); }
    static List<String> comparableKey(Map<String,Object> row) { return List.of(row.get("repository_id").toString(),(String)row.get("scan_type"),(String)row.get("scanner_name"),(String)row.get("scanner_version"),(String)row.get("rule_set_version")); }
    static Map<UUID,List<Map<String,Object>>> byArtifact(List<Map<String,Object>> findings) { var groups=new HashMap<UUID,List<Map<String,Object>>>();for(var row:findings)groups.computeIfAbsent((UUID)row.get("scan_artifact_id"),ignored->new ArrayList<>()).add(row);return groups; }
    static Map<String,Object> trendPoint(Map<String,Object> artifact,List<Map<String,Object>> findings,boolean camelCase) {
        return camelCase?map("artifactId",artifact.get("id").toString(),"targetSha",artifact.get("target_sha"),"createdAt",UtcTime.iso(artifact.get("created_at")),"contentHash",artifact.get("content_hash"),"findingCount",findings.size(),"severityCounts",counts(findings,"severity"),"statusCounts",counts(findings,"finding_status"),"coverage",SecurityStore.json(artifact,"coverage_json"))
            :map("artifact_id",artifact.get("id").toString(),"target_sha",artifact.get("target_sha"),"created_at",UtcTime.iso(artifact.get("created_at")),"content_hash",artifact.get("content_hash"),"finding_count",findings.size(),"severity_counts",counts(findings,"severity"),"status_counts",counts(findings,"finding_status"),"coverage",SecurityStore.json(artifact,"coverage_json"));
    }
    static Map<String,Long> counts(List<Map<String,Object>> rows,String field) { Map<String,Long> result=new TreeMap<>();rows.forEach(row->result.merge((String)row.get(field),1L,Long::sum));return result; }
    static Map<String,Object> map(Object... entries) { Map<String,Object> result=new LinkedHashMap<>();for(int i=0;i<entries.length;i+=2)result.put((String)entries[i],entries[i+1]);return result; }
    @SuppressWarnings("unchecked") static Map<String,Object> object(Object value) { if(!(value instanceof Map<?,?>))throw ApiInput.invalid();return (Map<String,Object>)value; }
    static Map<String,Object> optionalObject(Map<String,Object> body,String key) { return body.containsKey(key)?object(body.get(key)):Map.of(); }
    private static String clean(Map<String,Object> body,String key,int max) { String value=UnicodeText.strip(ApiInput.text(body,key,1,max));if(value.isEmpty())throw ApiInput.invalid();return value; }
}
