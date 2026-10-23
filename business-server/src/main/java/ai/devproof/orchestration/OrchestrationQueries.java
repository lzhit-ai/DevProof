package ai.devproof.orchestration;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.verification.*;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrchestrationQueries {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final VerificationOrchestration defaults;
    private final VerificationOrchestration.Data data;
    public OrchestrationQueries(JdbcTemplate jdbc,ProjectAccess access,VerificationOrchestration defaults,VerificationOrchestration.Data data) { this.jdbc=jdbc; this.access=access; this.defaults=defaults; this.data=data; }
    @Transactional public Map<String,Object> list(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); defaults.ensureProject(project,actor);
        List<Map<String,Object>> capabilities=new ArrayList<>(),tools=new ArrayList<>(),templates=new ArrayList<>();
        for(var row:jdbc.queryForList("SELECT c.*,v.id AS latest_id,v.version_no AS latest_no FROM agent_capabilities c LEFT JOIN LATERAL(SELECT id,version_no FROM agent_capability_versions WHERE capability_id=c.id ORDER BY version_no DESC LIMIT 1)v ON true WHERE c.project_id=? ORDER BY c.created_at",project)) {
            var item=fields(row,"id","key","name","description"); item.put("coreScope",row.get("core_scope")); item.put("kind",row.get("kind")); item.put("isLocked",row.get("is_locked"));
            item.put("isDefaultEnabled",row.get("is_default_enabled")); item.put("isActive",row.get("is_active")); item.put("latestVersionId",row.get("latest_id")); item.put("latestVersion",row.get("latest_no")); capabilities.add(item);
        }
        for(var row:jdbc.queryForList("SELECT * FROM agent_tools WHERE project_id=? ORDER BY created_at",project)) {
            var item=fields(row,"id","key","name"); item.put("toolType",row.get("tool_type")); item.put("endpointUrl",row.get("endpoint_url")); item.put("secretRef",row.get("secret_ref")); item.put("isSystem",row.get("is_system")); item.put("isActive",row.get("is_active")); tools.add(item);
        }
        for(var row:jdbc.queryForList("SELECT * FROM orchestration_templates WHERE project_id=? ORDER BY is_default DESC,created_at",project)) {
            var item=fields(row,"id","name","description","version"); item.put("assessmentProfile",row.get("assessment_profile")); item.put("isDefault",row.get("is_default")); item.put("isSystem",row.get("is_system"));
            List<Map<String,Object>> nodes=new ArrayList<>();
            for(var node:data.nodes((UUID)row.get("id"))) {
                Map<String,Object> value=new LinkedHashMap<>(); value.put("capabilityVersionId",node.get("capability_version_id")); value.put("capabilityKey",node.get("key")); value.put("capabilityName",node.get("name"));
                value.put("coreScope",node.get("core_scope")); value.put("displayOrder",node.get("display_order")); value.put("enabled",node.get("enabled")); value.put("locked",node.get("is_locked")); value.put("parameters",Json.object(data.parameters((UUID)node.get("id")))); nodes.add(value);
            }
            item.put("nodes",nodes); templates.add(item);
        }
        return Map.of("capabilities",capabilities,"tools",tools,"templates",templates);
    }
    @Transactional public Map<String,Object> latest(UUID project,UUID capability,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN");
        var rows=jdbc.queryForList("SELECT c.*,v.id AS version_id,v.version_no,v.prompt_template,v.input_schema,v.output_schema,v.parameter_schema,v.tool_bindings,v.content_hash FROM agent_capabilities c JOIN LATERAL(SELECT * FROM agent_capability_versions WHERE capability_id=c.id ORDER BY version_no DESC LIMIT 1)v ON true WHERE c.id=? AND c.project_id=?",capability,project);
        if(rows.isEmpty())throw missing(); var row=rows.getFirst();
        Map<String,Object> result=new LinkedHashMap<>(); result.put("capabilityId",capability); result.put("kind",row.get("kind")); result.put("isLocked",row.get("is_locked")); result.put("isActive",row.get("is_active"));
        result.put("versionId",row.get("version_id")); result.put("version",row.get("version_no")); result.put("promptTemplate",row.get("prompt_template"));
        result.put("inputSchema",Json.object(row.get("input_schema").toString())); result.put("outputSchema",Json.object(row.get("output_schema").toString())); result.put("parameterSchema",Json.object(row.get("parameter_schema").toString()));
        var bindings=objects(Json.read(row.get("tool_bindings").toString())); result.put("toolBindings",bindings);
        result.put("toolIds",bindings.stream().map(value->value.get("toolId")).filter(Objects::nonNull).toList()); result.put("contentHash",row.get("content_hash")); return result;
    }
    @Transactional public List<Map<String,Object>> bindings(UUID project,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); List<Map<String,Object>> result=new ArrayList<>();
        for(var row:jdbc.queryForList("""
            SELECT t.id,t.title,t.requirement_key,b.template_id,b.template_version,b.bound_at,o.name AS template_name,
              o.id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM orchestration_template_nodes n JOIN agent_capability_versions v ON v.id=n.capability_version_id JOIN agent_capabilities c ON c.id=v.capability_id WHERE n.template_id=o.id AND c.is_active=false) AS usable
            FROM verification_tasks t LEFT JOIN task_orchestration_bindings b ON b.task_id=t.id
            LEFT JOIN orchestration_templates o ON o.id=b.template_id AND o.project_id=t.project_id
            WHERE t.project_id=? ORDER BY t.updated_at DESC,t.created_at DESC
            """,project)) {
            Map<String,Object> item=new LinkedHashMap<>(); item.put("taskId",row.get("id")); item.put("taskTitle",row.get("title")); item.put("requirementKey",row.get("requirement_key"));
            item.put("templateId",row.get("template_id")); item.put("templateName",row.get("template_name")); item.put("templateVersion",row.get("template_version"));
            item.put("boundAt",row.get("bound_at") instanceof Timestamp stamp?stamp.toInstant().toString():null); item.put("isTemplateUsable",row.get("usable")); result.add(item);
        }
        return result;
    }
    @Transactional public Map<String,Object> run(UUID run,UUID actor) {
        var scopes=jdbc.queryForList("SELECT t.project_id FROM analysis_runs r JOIN input_snapshots s ON s.id=r.snapshot_id JOIN verification_cycles c ON c.id=s.cycle_id JOIN verification_tasks t ON t.id=c.task_id WHERE r.id=?",run);
        if(scopes.isEmpty())throw missing(); access.require((UUID)scopes.getFirst().get("project_id"),actor,"SUBMITTER","REVIEWER","ADMIN");
        var rows=jdbc.queryForList("SELECT *,template_snapshot::text AS template_json,nodes_snapshot::text AS nodes_json FROM analysis_run_orchestration_snapshots WHERE run_id=?",run);
        if(rows.isEmpty())throw missing(); var row=rows.getFirst();
        var body=row.get("raw_body") instanceof String?OrchestrationBodies.body(row):Map.of("template",Json.object((String)row.get("template_json")),"nodes",Json.read((String)row.get("nodes_json")));
        return Map.of("assessmentProfile",row.get("assessment_profile"),"contentHash",row.get("content_hash"),"template",body.get("template"),"nodes",body.get("nodes"),"rawBodyAvailable",row.get("raw_body")!=null);
    }
    @SuppressWarnings("unchecked") private static List<Map<String,Object>> objects(Object value) { return (List<Map<String,Object>>)value; }
    private static Map<String,Object> fields(Map<String,Object> row,String... keys) { Map<String,Object> out=new LinkedHashMap<>(); for(String key:keys)out.put(key,row.get(key)); return out; }
    private static ApiProblem missing() { return new ApiProblem(404,"RESOURCE_NOT_FOUND","能力版本或运行编排不存在"); }
}
