package ai.devproof.evidence;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Materials are immutable user submissions. A subsequent formal snapshot explicitly selects them. */
@Service
public class EvidenceMaterials {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final JavaArtifacts artifacts;
    private final ControlledArtifacts reader;
    private final BusinessAudit audit;
    private final long textLimit;
    public EvidenceMaterials(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,JavaArtifacts artifacts,
        ControlledArtifacts reader,BusinessAudit audit,@Value("${devproof.snapshot-text-max-bytes:8388608}") long textLimit) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.artifacts=artifacts; this.reader=reader; this.audit=audit; this.textLimit=textLimit;
    }
    @Transactional public CommandStore.Result manual(UUID cycle,UUID actor,CommandStore.Context command,String name,String content) {
        owners.requireJavaEvidenceMaterials(); var scope=cycle(cycle,actor,true);
        return commands.execute(command,201,()-> {
            editable(scope); byte[] raw=content.getBytes(StandardCharsets.UTF_8); UUID id=UUID.randomUUID(),project=(UUID)scope.get("project_id");
            var artifact=artifacts.save(project,"MANUAL_EVIDENCE","manual-evidence-v1","text/plain",raw);
            jdbc.update("INSERT INTO manual_evidence(id,project_id,cycle_id,logical_name,content_hash,artifact_uri,submitted_by,origin_type,origin_locator) VALUES(?,?,?,?,?,?,?,'MANUAL','{}'::jsonb)",id,project,cycle,name,artifact.get("content_hash"),artifact.get("storage_uri"),actor);
            audit.append(project,actor,"ManualEvidence",id,"MANUAL_EVIDENCE_SUBMITTED",command.correlationId(),Map.of("contentHash",artifact.get("content_hash"),"logicalName",name),null,null);
            return Map.of("id",id,"project_id",project,"cycle_id",cycle,"logical_name",name,"content_hash",artifact.get("content_hash"));
        });
    }
    @Transactional public CommandStore.Result external(UUID cycle,UUID actor,CommandStore.Context command,String type,String name,String sha,String content,Integer exitCode) {
        owners.requireJavaEvidenceMaterials(); var scope=cycle(cycle,actor,true);
        return commands.execute(command,201,()-> {
            editable(scope); UUID id=UUID.randomUUID(),project=(UUID)scope.get("project_id");
            var artifact=artifacts.save(project,"EXTERNAL_EVIDENCE","external-evidence-v1","text/plain",content.getBytes(StandardCharsets.UTF_8));
            jdbc.update("INSERT INTO external_evidence(id,project_id,cycle_id,evidence_type,logical_name,commit_sha,content_hash,artifact_uri,exit_code,submitted_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
                id,project,cycle,type,name,sha,artifact.get("content_hash"),artifact.get("storage_uri"),exitCode,actor);
            audit.append(project,actor,"ExternalEvidence",id,"EXTERNAL_EVIDENCE_IMPORTED",command.correlationId(),Map.of("type",type,"commitSha",sha,"contentHash",artifact.get("content_hash")),null,null);
            var result=new LinkedHashMap<>(Map.<String,Object>of("id",id,"project_id",project,"cycle_id",cycle,"evidence_type",type,"logical_name",name,"commit_sha",sha,"content_hash",artifact.get("content_hash")));
            result.put("exit_code",exitCode); return result;
        });
    }
    @Transactional public List<Map<String,Object>> executions(UUID run,UUID actor) {
        run(run,actor,false); List<Map<String,Object>> result=new ArrayList<>();
        for(var row:jdbc.queryForList("SELECT e.*,m.id AS imported_manual_evidence_id FROM agent_tool_executions e LEFT JOIN manual_evidence m ON m.source_tool_execution_id=e.id WHERE e.analysis_run_id=? ORDER BY e.created_at",run)) {
            var item=fields(row,"id","analysis_run_id","capability_key","tool_key","tool_type","content_hash","excerpt_safe","status","created_at","imported_manual_evidence_id");
            item.put("locator",Json.object(row.get("locator").toString())); result.add(item);
        }
        return result;
    }
    @Transactional public CommandStore.Result importExecution(UUID run,UUID execution,UUID actor,CommandStore.Context command,String name) {
        owners.requireJavaEvidenceMaterials(); var scope=run(run,actor,true); UUID project=(UUID)scope.get("project_id"),cycle=(UUID)scope.get("id");
        return commands.execute(command,201,()-> {
            editable(scope);
            if(!Set.of("SUCCEEDED","PARTIALLY_COMPLETED").contains(scope.get("run_status")))throw new ApiProblem(409,"STATE_CONFLICT","仅终态分析运行的工具结果可以显式导入");
            var rows=jdbc.queryForList("SELECT * FROM agent_tool_executions WHERE id=? AND analysis_run_id=? AND project_id=? AND input_snapshot_id=? FOR SHARE",execution,run,project,scope.get("snapshot_id"));
            if(rows.isEmpty())throw new ApiProblem(404,"RESOURCE_NOT_FOUND","临时工具结果不存在或不属于当前运行"); var tool=rows.getFirst();
            var prior=jdbc.queryForList("SELECT * FROM manual_evidence WHERE source_tool_execution_id=?",execution);
            if(!prior.isEmpty()) {
                if(!project.equals(prior.getFirst().get("project_id")) || !cycle.equals(prior.getFirst().get("cycle_id")))throw stale();
                return imported(prior.getFirst());
            }
            String actual=reader.text((String)tool.get("artifact_uri"),textLimit,(String)tool.get("content_hash"));
            var artifact=artifacts.save(project,"MANUAL_EVIDENCE","manual-evidence-v1","text/plain",actual.getBytes(StandardCharsets.UTF_8));
            UUID id=UUID.randomUUID(); String logicalName=UnicodeText.strip(name); if(logicalName.isEmpty())throw ApiInput.invalid();
            var origin=Map.of("toolExecutionId",execution.toString(),"analysisRunId",run.toString(),"capabilityKey",tool.get("capability_key"),"toolKey",tool.get("tool_key"),"toolResponseHash",tool.get("content_hash"));
            jdbc.update("INSERT INTO manual_evidence(id,project_id,cycle_id,logical_name,content_hash,artifact_uri,submitted_by,origin_type,origin_locator,source_tool_execution_id) VALUES(?,?,?,?,?,?,?,'AGENT_TOOL_IMPORT',CAST(? AS jsonb),?)",
                id,project,cycle,logicalName,artifact.get("content_hash"),artifact.get("storage_uri"),actor,Json.canonical(origin),execution);
            audit.append(project,actor,"AgentToolExecution",execution,"AGENT_TOOL_RESULT_IMPORTED",command.correlationId(),Map.of("manualEvidenceId",id.toString(),"contentHash",artifact.get("content_hash")),null,null);
            audit.append(project,actor,"ManualEvidence",id,"MANUAL_EVIDENCE_SUBMITTED",command.correlationId(),Map.of("contentHash",artifact.get("content_hash"),"logicalName",logicalName,"originType","AGENT_TOOL_IMPORT","toolExecutionId",execution.toString()),null,null);
            return Map.of("manual_evidence_id",id,"cycle_id",cycle,"content_hash",artifact.get("content_hash"),"origin_type","AGENT_TOOL_IMPORT");
        });
    }
    @Transactional public Map<String,Object> citation(UUID snapshot,UUID evidence,UUID actor) {
        var snapshots=jdbc.queryForList("SELECT t.project_id FROM input_snapshots s JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE s.id=?",snapshot);
        if(snapshots.isEmpty())throw new ApiProblem(422,"RESOURCE_NOT_FOUND","输入快照不存在"); UUID project=(UUID)snapshots.getFirst().get("project_id");
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        var rows=jdbc.queryForList("SELECT * FROM evidence_items WHERE id=? AND snapshot_id=? AND project_id=?",evidence,snapshot,project);
        if(rows.isEmpty())throw invalidCitation(); var row=rows.getFirst();
        if("TOOL".equals(row.get("source_type")) || "HTTP_QUERY".equals(row.get("evidence_kind")) || !Set.of("EXACT","APPROXIMATE","UNAVAILABLE").contains(row.get("locator_precision")))throw invalidCitation();
        var result=fields(row,"id","snapshot_id","source_type","evidence_kind","excerpt_safe","locator_precision"); result.put("locator",Json.object(row.get("locator").toString())); return result;
    }
    private Map<String,Object> cycle(UUID cycle,UUID actor,boolean write) {
        var refs=jdbc.queryForList("SELECT t.project_id FROM verification_cycles c JOIN verification_tasks t ON t.id=c.task_id WHERE c.id=?",cycle);
        if(refs.isEmpty())throw missing(); UUID project=(UUID)refs.getFirst().get("project_id");
        access.require(project,actor,write?new String[]{"SUBMITTER","ADMIN"}:new String[]{"SUBMITTER","REVIEWER","ADMIN"});
        var rows=jdbc.queryForList("SELECT * FROM verification_cycles WHERE id=?"+(write?" FOR UPDATE":""),cycle);
        if(rows.isEmpty())throw missing(); var result=rows.getFirst(); result.put("project_id",project); return result;
    }
    private Map<String,Object> run(UUID run,UUID actor,boolean write) {
        var rows=jdbc.queryForList("SELECT r.run_status,r.snapshot_id,s.cycle_id FROM analysis_runs r JOIN input_snapshots s ON s.id=r.snapshot_id WHERE r.id=?",run);
        if(rows.isEmpty())throw missing(); var ref=rows.getFirst(); var scope=cycle((UUID)ref.get("cycle_id"),actor,write);
        if(write)ref=jdbc.queryForMap("SELECT run_status,snapshot_id FROM analysis_runs WHERE id=?",run);
        scope.put("run_status",ref.get("run_status")); scope.put("snapshot_id",ref.get("snapshot_id")); return scope;
    }
    private static void editable(Map<String,Object> scope) { if(!Set.of("DRAFT","NEEDS_EVIDENCE","NEEDS_CONFIRMATION").contains(scope.get("business_status")))throw new ApiProblem(409,"STATE_CONFLICT","当前轮次不能再提交补证，请使用可补证轮次创建新的正式快照"); }
    private static Map<String,Object> imported(Map<String,Object> row) { return Map.of("manual_evidence_id",row.get("id"),"cycle_id",row.get("cycle_id"),"content_hash",row.get("content_hash"),"origin_type",row.get("origin_type")); }
    private static Map<String,Object> fields(Map<String,Object> row,String... keys) { Map<String,Object> result=new LinkedHashMap<>(); for(String key:keys) { Object value=row.get(key); result.put(key,value instanceof Timestamp stamp?stamp.toInstant().toString():value); } return result; }
    private static ApiProblem missing() { return new ApiProblem(404,"RESOURCE_NOT_FOUND","核验轮次或分析运行不存在"); }
    private static ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","已有导入材料不属于当前运行轮次"); }
    private static ApiProblem invalidCitation() { return new ApiProblem(422,"CITATION_INVALID","证据不属于当前快照、定位无效或仍是未导入冻结的临时工具结果"); }
}
