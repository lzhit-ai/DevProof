package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.apache.ibatis.annotations.*;
import org.springframework.stereotype.Service;

@Service
public class VerificationOrchestration {
    public static final Set<String> CORE=Set.of("requirement-claim-core","delivery-git-diff","evidence-reconciliation");
    public static final Set<String> BUILT_IN=Set.of("requirement-claim-core","delivery-git-diff","evidence-reconciliation","ci-evidence-import","risk-scan","model-link-proposal","report-draft");
    public static boolean validRegistration(String key,String kind,boolean locked,String scope) {
        if("CUSTOM".equals(kind) && (!"SHARED".equals(scope) || BUILT_IN.contains(key)))return false;
        if(CORE.contains(key))return "SYSTEM".equals(kind) && locked && switch(key) {
            case "requirement-claim-core"->"REQUIREMENT".equals(scope);
            case "delivery-git-diff"->"DELIVERY".equals(scope);
            default->"SHARED".equals(scope);
        };
        return true;
    }
    private record Core(String key,String name,String scope,boolean locked,String description,String tool) {}
    private static final List<Core> DEFAULTS=List.of(
        new Core("requirement-claim-core","需求/验收核验核心","REQUIREMENT",true,"从冻结的需求和验收资料提取可引用 Claim。","document-retrieval"),
        new Core("delivery-git-diff","Git Diff 代码证据","DELIVERY",true,"读取冻结 Git 范围并生成可定位的代码证据。","git-diff-reader"),
        new Core("ci-evidence-import","CI 测试与构建证据","DELIVERY",false,"导入与冻结目标提交绑定的测试和构建证据。","ci-evidence-reader"),
        new Core("risk-scan","交付风险扫描","SHARED",false,"根据已授权证据标记需要人工确认的交付风险。","evidence-query"),
        new Core("model-link-proposal","证据关联建议","SHARED",false,"由模型提出候选关联，不能直接决定正式结论。","evidence-query"),
        new Core("evidence-reconciliation","证据裁决与 Coverage","SHARED",true,"校验引用、应用权威规则并生成正式核验结果。","evidence-query"),
        new Core("report-draft","报告草稿","SHARED",false,"把已持久化结果整理为可编辑报告草稿。","evidence-query"));
    @Mapper public interface Data {
        @Select("SELECT t.* FROM task_orchestration_bindings b JOIN orchestration_templates t ON t.id=b.template_id WHERE b.task_id=#{id} FOR SHARE OF b,t") Map<String,Object> bound(UUID id);
        @Select("SELECT * FROM orchestration_templates WHERE project_id=#{id} AND is_default=true FOR SHARE") Map<String,Object> defaultTemplate(UUID id);
        @Select("SELECT * FROM orchestration_templates WHERE id=#{id} AND project_id=#{project} FOR SHARE") Map<String,Object> selectedTemplate(UUID id,UUID project);
        @Select("SELECT n.*,v.version_no,v.prompt_template,v.tool_bindings::text AS tools_json,c.id AS capability_id,c.key,c.name,c.kind,c.core_scope AS capability_scope,c.is_locked,c.is_active,c.project_id FROM orchestration_template_nodes n JOIN agent_capability_versions v ON v.id=n.capability_version_id JOIN agent_capabilities c ON c.id=v.capability_id WHERE n.template_id=#{id} ORDER BY n.display_order FOR SHARE OF n,v,c") List<Map<String,Object>> nodes(UUID id);
        @Select("SELECT pg_advisory_xact_lock(hashtextextended(CAST(#{id} AS text),61))") Object lockConfiguration(UUID id);
        @Insert("INSERT INTO agent_tools(id,project_id,key,name,tool_type,is_system,is_active,created_by,input_schema,output_schema) VALUES(#{id},#{project},#{key},#{name},#{type},true,true,#{actor},'{}','{}')") void tool(UUID id,UUID project,String key,String name,String type,UUID actor);
        @Insert("INSERT INTO agent_capabilities(id,project_id,key,name,description,core_scope,kind,is_locked,is_default_enabled,is_active,created_by) VALUES(#{id},#{project},#{key},#{name},#{description},#{scope},'SYSTEM',#{locked},true,true,#{actor})") void capability(UUID id,UUID project,String key,String name,String description,String scope,boolean locked,UUID actor);
        @Insert("INSERT INTO agent_capability_versions(id,capability_id,version_no,prompt_template,input_schema,output_schema,tool_bindings,parameter_schema,content_hash,created_by) VALUES(#{id},#{capability},1,'','{}','{}',CAST(#{tools} AS jsonb),'{}',#{hash},#{actor})") void version(UUID id,UUID capability,String tools,String hash,UUID actor);
        @Insert("INSERT INTO orchestration_templates(id,project_id,name,description,assessment_profile,version,is_default,is_system,created_by) VALUES(#{id},#{project},'默认交付核验','固定双核、锁定 Git Diff，并按证据协议执行的默认模板。','DELIVERY_VERIFICATION',1,true,true,#{actor})") void template(UUID id,UUID project,UUID actor);
        @Insert("INSERT INTO orchestration_template_nodes(id,template_id,capability_version_id,core_scope,display_order,enabled,parameters) VALUES(#{id},#{template},#{version},#{scope},#{order},true,CAST(#{parameters} AS jsonb))") void node(UUID id,UUID template,UUID version,String scope,int order,String parameters);
        @Insert("INSERT INTO task_orchestration_bindings(id,task_id,template_id,template_version,bound_by) VALUES(#{id},#{task},#{template},#{version},#{actor})") void bind(UUID id,UUID task,UUID template,int version,UUID actor);
        @Select("SELECT parameters::text FROM orchestration_template_nodes WHERE id=#{id}") String parameters(UUID id);
        @Insert("INSERT INTO analysis_run_orchestration_snapshots(id,run_id,template_id,template_version,assessment_profile,content_hash,template_snapshot,nodes_snapshot,raw_body) VALUES(#{id},#{run},#{template},#{version},'DELIVERY_VERIFICATION',#{hash},CAST(#{identity} AS jsonb),CAST(#{nodes} AS jsonb),#{raw})")
        void freeze(UUID id,UUID run,UUID template,int version,String hash,String identity,String nodes,String raw);
    }
    public record Frozen(Map<String,Object> template,List<Map<String,Object>> nodes,String hash,String raw) {}
    private final Data data;
    private final BusinessOwnership owners;
    public VerificationOrchestration(Data data,BusinessOwnership owners) { this.data=data; this.owners=owners; }
    public void ensureProject(UUID project,UUID actor) {
        owners.requireJavaOrchestration();
        data.lockConfiguration(project); if(data.defaultTemplate(project)==null)createDefault(project,actor);
    }
    public void bindNewTask(UUID task,UUID project,UUID actor,UUID selected) {
        owners.requireJavaOrchestration();
        if(selected!=null) {
            Map<String,Object> template=data.selectedTemplate(selected,project);
            if(template==null || !"DELIVERY_VERIFICATION".equals(template.get("assessment_profile")))throw invalid("任务编排模板不属于当前项目的交付核验范围");
            data.bind(UUID.randomUUID(),task,selected,((Number)template.get("version")).intValue(),actor);
        }
        load(task,project,actor);
    }
    public Frozen load(UUID task,UUID project,UUID actor) {
        owners.requireJavaOrchestration();
        Map<String,Object> template=data.bound(task);
        if(template==null) { data.lockConfiguration(project); template=data.bound(task); if(template==null) {
            template=data.defaultTemplate(project); if(template==null) { createDefault(project,actor); template=data.defaultTemplate(project); }
            data.bind(UUID.randomUUID(),task,(UUID)template.get("id"),((Number)template.get("version")).intValue(),actor);
        }}
        if(!project.equals(template.get("project_id")) || !"DELIVERY_VERIFICATION".equals(template.get("assessment_profile")))throw invalid("任务编排不属于当前交付核验范围");
        List<Map<String,Object>> nodes=new ArrayList<>(); Set<String> enabled=new HashSet<>(), versions=new HashSet<>(),capabilities=new HashSet<>();
        for(Map<String,Object> row:data.nodes((UUID)template.get("id"))) {
            if(!project.equals(row.get("project_id")) || !Boolean.TRUE.equals(row.get("is_active")))throw invalid("能力版本已停用或不属于项目");
            if(!Objects.equals(row.get("core_scope"),row.get("capability_scope")) || !validRegistration((String)row.get("key"),(String)row.get("kind"),Boolean.TRUE.equals(row.get("is_locked")),(String)row.get("capability_scope")))throw invalid("能力身份或固定核心作用域无效");
            if(!versions.add(row.get("capability_version_id").toString()))throw invalid("同一能力版本不能重复出现");
            if(!capabilities.add(row.get("capability_id").toString()))throw invalid("同一能力不能同时编排多个版本");
            if(Boolean.TRUE.equals(row.get("is_locked")) && !Boolean.TRUE.equals(row.get("enabled")))throw invalid("系统主干能力不能停用");
            if(Boolean.TRUE.equals(row.get("enabled")))enabled.add((String)row.get("key"));
            Map<String,Object> node=new LinkedHashMap<>();
            node.put("capabilityId",row.get("capability_id").toString()); node.put("capabilityKey",row.get("key")); node.put("capabilityName",row.get("name"));
            node.put("capabilityVersionId",row.get("capability_version_id").toString()); node.put("capabilityVersion",row.get("version_no"));
            node.put("coreScope",row.get("core_scope")); node.put("displayOrder",row.get("display_order")); node.put("enabled",row.get("enabled")); node.put("locked",row.get("is_locked"));
            node.put("promptTemplate",row.get("prompt_template")); node.put("tools",Json.read((String)row.get("tools_json"))); node.put("parameters",Json.object(data.parameters((UUID)row.get("id")))); nodes.add(node);
        }
        if(!enabled.containsAll(CORE))throw invalid("编排缺少固定核验主干");
        Map<String,Object> identity=Map.of("id",template.get("id").toString(),"name",template.get("name"),"version",template.get("version"),"assessmentProfile",template.get("assessment_profile"));
        String raw=Json.canonical(Map.of("template",identity,"nodes",nodes));
        return new Frozen(identity,nodes,Json.hash(raw),raw);
    }
    public void freeze(UUID run,UUID id,Frozen frozen) {
        owners.requireJavaOrchestration();
        data.freeze(id,run,UUID.fromString((String)frozen.template().get("id")),((Number)frozen.template().get("version")).intValue(),frozen.hash(),Json.canonical(frozen.template()),Json.canonical(frozen.nodes()),frozen.raw());
    }
    private void createDefault(UUID project,UUID actor) {
        Map<String,Map<String,Object>> tools=new LinkedHashMap<>();
        for(String[] spec:List.of(new String[]{"document-retrieval","资料检索","DOCUMENT_RETRIEVAL"},new String[]{"git-diff-reader","Git Diff 只读","GIT_DIFF"},new String[]{"ci-evidence-reader","CI 证据读取","CI_EVIDENCE"},new String[]{"evidence-query","证据查询","EVIDENCE_QUERY"})) {
            UUID id=UUID.randomUUID(); data.tool(id,project,spec[0],spec[1],spec[2],actor);
            Map<String,Object> binding=new LinkedHashMap<>(); binding.put("toolId",id.toString()); binding.put("key",spec[0]); binding.put("type",spec[2]); binding.put("endpointUrl",null); binding.put("secretRef",null); binding.put("inputSchema",Map.of()); binding.put("outputSchema",Map.of()); tools.put(spec[0],binding);
        }
        UUID template=UUID.randomUUID(); data.template(template,project,actor); int order=0;
        for(Core core:DEFAULTS) {
            UUID capability=UUID.randomUUID(), version=UUID.randomUUID(); List<Map<String,Object>> bindings=List.of(tools.get(core.tool()));
            data.capability(capability,project,core.key(),core.name(),core.description(),core.scope(),core.locked(),actor);
            String hash=Json.hash(Json.write(Map.of("key",core.key(),"prompt","","input",Map.of(),"output",Map.of(),"tools",bindings,"parameters",Map.of())));
            data.version(version,capability,Json.write(bindings),hash,actor); data.node(UUID.randomUUID(),template,version,core.scope(),++order,Json.write(Map.of("locked",core.locked())));
        }
    }
    private ApiProblem invalid(String message) { return new ApiProblem(409,"ORCHESTRATION_INVALID",message); }
}
