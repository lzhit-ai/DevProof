package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Rechecks the live attempt after external I/O before registering any actual tool material. */
@Service
public class VerificationToolStore {
    private final VerificationToolScope scope;
    private final BusinessOwnership owners;
    private final JdbcTemplate jdbc;
    private final JavaArtifacts artifacts;
    private final ControlledArtifacts reader;
    public VerificationToolStore(VerificationToolScope scope,BusinessOwnership owners,JdbcTemplate jdbc,JavaArtifacts artifacts,ControlledArtifacts reader) {
        this.scope=scope; this.owners=owners; this.jdbc=jdbc; this.artifacts=artifacts; this.reader=reader;
    }
    private Map<String,Object> live(Map<String,Object> payload) { scope.revalidate(payload); owners.requireJavaVerification(); return scope.require(payload); }
    @Transactional public Map<String,Object> tool(Map<String,Object> payload,String capability,String key) {
        UUID run=(UUID)live(payload).get("id");
        var rows=jdbc.queryForList("SELECT *,locator::text AS locator_json FROM agent_tool_executions WHERE analysis_run_id=? AND capability_key=? AND tool_key=?",run,capability,key);
        return rows.isEmpty()?null:temporary(rows.getFirst(),true);
    }
    @Transactional public Map<String,Object> recordTool(Map<String,Object> payload,String capability,String key,byte[] bytes,String media,Map<String,Object> locator) {
        Map<String,Object> run=live(payload);
        var rows=jdbc.queryForList("SELECT *,locator::text AS locator_json FROM agent_tool_executions WHERE analysis_run_id=? AND capability_key=? AND tool_key=?",run.get("id"),capability,key);
        if(!rows.isEmpty())return temporary(rows.getFirst(),true);
        Map<String,Object> artifact=artifacts.save((UUID)run.get("project_id"),"AGENT_TOOL_RESPONSE","http-tool-response-v2",media,bytes);
        UUID id=UUID.randomUUID();
        jdbc.update("INSERT INTO agent_tool_executions(id,project_id,analysis_run_id,input_snapshot_id,capability_key,tool_key,tool_type,content_hash,artifact_uri,excerpt_safe,locator,status) VALUES(?,?,?,?,?,?,'HTTP_QUERY',?,?,?,CAST(? AS jsonb),'SUCCEEDED')",
            id,run.get("project_id"),run.get("id"),run.get("snapshot_id"),capability,key,artifact.get("content_hash"),artifact.get("storage_uri"),SafeExcerpt.text(new String(bytes,StandardCharsets.UTF_8),12000),Json.write(locator));
        return temporary(jdbc.queryForMap("SELECT *,locator::text AS locator_json FROM agent_tool_executions WHERE id=?",id),false);
    }
    private Map<String,Object> temporary(Map<String,Object> row,boolean replay) {
        return Map.of("toolExecutionId",row.get("id").toString(),"toolKey",row.get("tool_key"),"contentHash",row.get("content_hash"),"excerpt",row.get("excerpt_safe"),"locator",Json.object((String)row.get("locator_json")),"evidenceRole","TEMPORARY","replayed",replay);
    }
    @Transactional public Map<String,Object> context(Map<String,Object> payload) {
        UUID run=(UUID)live(payload).get("id");
        var rows=jdbc.queryForList("SELECT a.*,r.request_hash FROM analysis_run_context_artifacts r JOIN artifact_objects a ON a.id=r.artifact_id WHERE r.analysis_run_id=? AND r.round_no=1",run);
        if(rows.isEmpty())return null;
        Map<String,Object> row=rows.getFirst();
        return contextResult(row,Json.object(reader.text((String)row.get("storage_uri"),scope.limit(payload,"contextMaxTotalBytes")*2L,(String)row.get("content_hash"))),true);
    }
    @Transactional public Map<String,Object> recordContext(Map<String,Object> payload,String requestHash,Map<String,Object> content) {
        Map<String,Object> run=live(payload); var rows=jdbc.queryForList("SELECT artifact_id FROM analysis_run_context_artifacts WHERE analysis_run_id=? AND round_no=1",run.get("id"));
        if(!rows.isEmpty())return context(payload);
        byte[] raw=Json.write(content).getBytes(StandardCharsets.UTF_8);
        if(raw.length>scope.limit(payload,"contextMaxTotalBytes")*2L)throw new ApiProblem(422,"TOOL_RESPONSE_TOO_LARGE","补充上下文超过冻结预算");
        Map<String,Object> artifact=artifacts.save((UUID)run.get("project_id"),"CODE_CONTEXT_SUPPLEMENT","run-context-v2","application/json",raw);
        jdbc.update("INSERT INTO analysis_run_context_artifacts(id,analysis_run_id,artifact_id,round_no,request_hash) VALUES(?,?,?,1,?)",UUID.randomUUID(),run.get("id"),artifact.get("id"),requestHash);
        return contextResult(artifact,content,false);
    }
    private Map<String,Object> contextResult(Map<String,Object> artifact,Map<String,Object> content,boolean replay) {
        return Map.of("contexts",content.get("contexts"),"details",Map.of("artifactId",artifact.get("id").toString(),"contextCount",((List<?>)content.get("contexts")).size(),"skipped",content.getOrDefault("skipped",List.of()),"replayed",replay));
    }
}
