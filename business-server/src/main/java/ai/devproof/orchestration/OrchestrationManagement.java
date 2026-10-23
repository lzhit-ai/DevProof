package ai.devproof.orchestration;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.verification.*;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Versions and templates are business configuration; only Java can author them after handoff. */
@Service
public class OrchestrationManagement {
    private final JdbcTemplate jdbc;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final VerificationOrchestration defaults;
    private final ToolEndpointPolicy policy;
    public OrchestrationManagement(JdbcTemplate jdbc,ProjectAccess access,BusinessOwnership owners,CommandStore commands,
        BusinessAudit audit,VerificationOrchestration defaults,ToolEndpointPolicy policy) {
        this.jdbc=jdbc; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit; this.defaults=defaults; this.policy=policy;
    }
    @Transactional public CommandStore.Result tool(UUID project,UUID actor,CommandStore.Context command,Map<String,Object> input) {
        if("HTTP_QUERY".equals(input.get("tool_type")))access.require(project,actor,"ADMIN");
        return write(project,actor,command,201,()-> {
            String key=key(input),name=name(input),type=ApiInput.text(input,"tool_type",1,32);
            if(!Set.of("DOCUMENT_RETRIEVAL","GIT_DIFF","CI_EVIDENCE","EVIDENCE_QUERY","HTTP_QUERY").contains(type))throw ApiInput.invalid();
            String endpoint=ApiInput.optionalText(input,"endpoint_url",2000),ref=ApiInput.optionalText(input,"secret_ref",160);
            if(ref!=null && ref.isEmpty())ref=null;
            if("HTTP_QUERY".equals(type)) {
                access.require(project,actor,"ADMIN"); if(endpoint==null || endpoint.isEmpty())throw ApiInput.invalid(); endpoint=policy.endpoint(endpoint);
            } else if(endpoint!=null && !endpoint.isEmpty())throw new ApiProblem(422,"INPUT_INVALID","内置只读工具不能配置外部端点");
            policy.reference(ref,"HTTP_QUERY".equals(type)); unique("agent_tools","key",project,key,"项目内工具标识已存在");
            UUID id=UUID.randomUUID();
            jdbc.update("INSERT INTO agent_tools(id,project_id,key,name,tool_type,endpoint_url,secret_ref,input_schema,output_schema,is_system,is_active,created_by) VALUES(?,?,?,?,?,?,?,CAST(? AS jsonb),CAST(? AS jsonb),false,true,?)",
                id,project,key,name,type,endpoint,ref,Json.canonical(object(input,"input_schema")),Json.canonical(object(input,"output_schema")),actor);
            audit.append(project,actor,"AgentTool",id,"AGENT_TOOL_CREATED",command.correlationId(),Map.of(),null,null);
            return Map.of("id",id,"key",key,"name",name,"toolType",type);
        });
    }
    @Transactional public CommandStore.Result capability(UUID project,UUID actor,CommandStore.Context command,Map<String,Object> input) {
        return write(project,actor,command,201,()-> {
            if(!"SHARED".equals(input.get("core_scope")))throw new ApiProblem(422,"INPUT_INVALID","自定义 Agent 只能作为 SHARED 外围能力");
            String key=key(input),name=name(input),description=UnicodeText.strip(optional(input,"description",4000));
            if(VerificationOrchestration.BUILT_IN.contains(key))throw new ApiProblem(409,"STATE_CONFLICT","系统能力标识已保留");
            unique("agent_capabilities","key",project,key,"项目内能力标识已存在"); UUID id=UUID.randomUUID();
            jdbc.update("INSERT INTO agent_capabilities(id,project_id,key,name,description,core_scope,kind,is_locked,is_default_enabled,is_active,created_by) VALUES(?,?,?,?,?,'SHARED','CUSTOM',false,true,true,?)",id,project,key,name,description,actor);
            version(project,id,key,actor,1,input);
            audit.append(project,actor,"AgentCapability",id,"AGENT_CAPABILITY_CREATED",command.correlationId(),Map.of(),null,null);
            return Map.of("id",id,"key",key,"name",name,"coreScope","SHARED");
        });
    }
    @Transactional public CommandStore.Result nextVersion(UUID project,UUID capability,UUID actor,CommandStore.Context command,Map<String,Object> input) {
        return write(project,actor,command,201,()-> {
            var row=requireCapability(project,capability);
            if("SYSTEM".equals(row.get("kind")))throw new ApiProblem(403,"AUTH_FORBIDDEN","系统主干能力不能编辑 Prompt 或工具授权");
            if(!Boolean.TRUE.equals(row.get("is_active")))throw new ApiProblem(409,"STATE_CONFLICT","已停用能力不能再创建版本");
            int next=jdbc.queryForObject("SELECT coalesce(max(version_no),0)+1 FROM agent_capability_versions WHERE capability_id=?",Integer.class,capability);
            var result=version(project,capability,(String)row.get("key"),actor,next,input);
            audit.append(project,actor,"AgentCapability",capability,"AGENT_CAPABILITY_VERSION_CREATED",command.correlationId(),Map.of("version",next),null,null); return result;
        });
    }
    @Transactional public CommandStore.Result deactivate(UUID project,UUID capability,UUID actor,CommandStore.Context command) {
        return write(project,actor,command,200,()-> {
            var row=requireCapability(project,capability);
            if(!"CUSTOM".equals(row.get("kind")) || Boolean.TRUE.equals(row.get("is_locked")))throw new ApiProblem(403,"AUTH_FORBIDDEN","系统能力不能停用");
            if(Boolean.TRUE.equals(row.get("is_active"))) {
                jdbc.update("UPDATE agent_capabilities SET is_active=false,updated_at=clock_timestamp() WHERE id=?",capability);
                audit.append(project,actor,"AgentCapability",capability,"AGENT_CAPABILITY_DEACTIVATED",command.correlationId(),Map.of(),null,null);
            }
            return Map.of("id",capability,"isActive",false);
        });
    }
    @Transactional public CommandStore.Result template(UUID project,UUID actor,CommandStore.Context command,Map<String,Object> input) {
        return write(project,actor,command,201,()-> {
            String name=name(input),description=UnicodeText.strip(optional(input,"description",4000));
            String profile=input.containsKey("assessment_profile")?ApiInput.text(input,"assessment_profile",1,48):"DELIVERY_VERIFICATION";
            if(!Set.of("DELIVERY_VERIFICATION","PROJECT_STATUS_SUMMARY","SECURITY_BASELINE","QUALITY_TREND").contains(profile))throw ApiInput.invalid();
            if(!"DELIVERY_VERIFICATION".equals(profile))throw new ApiProblem(409,"ASSESSMENT_PROFILE_NOT_ENABLED","该运行配置尚未开放模板编排");
            unique("orchestration_templates","name",project,name,"项目内编排模板名称已存在");
            var resolved=resolve(project,nodes(input)); UUID id=UUID.randomUUID();
            jdbc.update("INSERT INTO orchestration_templates(id,project_id,name,description,assessment_profile,is_default,is_system,version,created_by) VALUES(?,?,?,?,?,false,false,1,?)",id,project,name,description,profile,actor);
            int order=0;
            for(var node:resolved)jdbc.update("INSERT INTO orchestration_template_nodes(id,template_id,capability_version_id,core_scope,display_order,enabled,parameters) VALUES(?,?,?,?,?,?,CAST(? AS jsonb))",
                UUID.randomUUID(),id,node.get("version"),node.get("scope"),++order,node.get("enabled"),Json.canonical(node.get("parameters")));
            audit.append(project,actor,"OrchestrationTemplate",id,"ORCHESTRATION_TEMPLATE_CREATED",command.correlationId(),Map.of(),null,null);
            return Map.of("id",id,"name",name,"assessmentProfile",profile,"version",1);
        });
    }
    @Transactional public CommandStore.Result bind(UUID task,UUID template,UUID actor,CommandStore.Context command) {
        var tasks=jdbc.queryForList("SELECT project_id FROM verification_tasks WHERE id=?",task);
        if(tasks.isEmpty())throw missing(); UUID project=(UUID)tasks.getFirst().get("project_id");
        return write(project,actor,command,200,()-> {
            jdbc.queryForList("SELECT id FROM verification_tasks WHERE id=? AND project_id=? FOR UPDATE",task,project);
            var rows=jdbc.queryForList("SELECT * FROM orchestration_templates WHERE id=? AND project_id=? FOR SHARE",template,project);
            if(rows.isEmpty())throw missing(); var row=rows.getFirst();
            if(!"DELIVERY_VERIFICATION".equals(row.get("assessment_profile")))throw new ApiProblem(409,"ASSESSMENT_PROFILE_NOT_ENABLED","该模板尚未开放交付核验");
            List<Map<String,Object>> specs=new ArrayList<>();
            for(var node:jdbc.queryForList("SELECT capability_version_id,enabled,parameters FROM orchestration_template_nodes WHERE template_id=? ORDER BY display_order",template))
                specs.add(Map.of("capability_version_id",node.get("capability_version_id").toString(),"enabled",node.get("enabled"),"parameters",Json.object(node.get("parameters").toString())));
            resolve(project,specs); int version=((Number)row.get("version")).intValue();
            jdbc.update("INSERT INTO task_orchestration_bindings(id,task_id,template_id,template_version,bound_by) VALUES(?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET template_id=EXCLUDED.template_id,template_version=EXCLUDED.template_version,bound_by=EXCLUDED.bound_by",
                UUID.randomUUID(),task,template,version,actor);
            audit.append(project,actor,"VerificationTask",task,"TASK_ORCHESTRATION_BOUND",command.correlationId(),Map.of("templateId",template.toString(),"templateVersion",version),null,null);
            return Map.of("taskId",task,"templateId",template,"templateVersion",version);
        });
    }
    private CommandStore.Result write(UUID project,UUID actor,CommandStore.Context command,int status,Supplier<Map<String,Object>> action) {
        owners.requireJavaOrchestration(); access.require(project,actor,"SUBMITTER","ADMIN");
        jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(CAST(? AS text),61))",Object.class,project);
        return commands.execute(command,status,action);
    }
    private Map<String,Object> version(UUID project,UUID capability,String key,UUID actor,int number,Map<String,Object> input) {
        String prompt=optional(input,"prompt_template",20000); Map<String,Object> in=object(input,"input_schema"),out=object(input,"output_schema"),parameters=object(input,"parameter_schema");
        List<UUID> ids=ApiInput.uuids(input,"tool_ids",20); if(new HashSet<>(ids).size()!=ids.size())throw new ApiProblem(422,"INPUT_INVALID","工具不能重复授权");
        List<Map<String,Object>> tools=new ArrayList<>();
        if(!ids.isEmpty()) {
            List<Object> args=new ArrayList<>(ids); args.add(project);
            String placeholders=String.join(",",Collections.nCopies(ids.size(),"?"));
            for(var tool:jdbc.queryForList("SELECT * FROM agent_tools WHERE id IN ("+placeholders+") AND project_id=? AND is_active=true FOR SHARE",args.toArray()))tools.add(toolBinding(tool));
        }
        if(tools.size()!=ids.size())throw new ApiProblem(422,"INPUT_INVALID","工具不存在、不属于项目或已停用");
        String hash=Json.hash(Json.canonical(Map.of("key",key,"prompt",prompt,"input",in,"output",out,"tools",tools,"parameters",parameters))); UUID id=UUID.randomUUID();
        jdbc.update("INSERT INTO agent_capability_versions(id,capability_id,version_no,prompt_template,input_schema,output_schema,tool_bindings,parameter_schema,content_hash,created_by) VALUES(?,?,?,?,CAST(? AS jsonb),CAST(? AS jsonb),CAST(? AS jsonb),CAST(? AS jsonb),?,?)",
            id,capability,number,prompt,Json.canonical(in),Json.canonical(out),Json.canonical(tools),Json.canonical(parameters),hash,actor);
        return Map.of("id",id,"version",number,"contentHash",hash);
    }
    private List<Map<String,Object>> resolve(UUID project,List<Map<String,Object>> nodes) {
        if(nodes.isEmpty() || nodes.size()>30)throw ApiInput.invalid(); Set<UUID> versions=new HashSet<>(),capabilities=new HashSet<>(); Set<String> enabled=new HashSet<>(); List<Map<String,Object>> result=new ArrayList<>();
        for(var node:nodes) {
            UUID version=ApiInput.uuid(node.get("capability_version_id"));
            var rows=jdbc.queryForList("SELECT v.id,c.id AS capability,c.key,c.core_scope,c.kind,c.is_locked FROM agent_capability_versions v JOIN agent_capabilities c ON c.id=v.capability_id WHERE v.id=? AND c.project_id=? AND c.is_active=true FOR SHARE OF v,c",version,project);
            if(rows.isEmpty() || !versions.add(version) || !capabilities.add((UUID)rows.getFirst().get("capability")))throw new ApiProblem(422,"INPUT_INVALID","能力不存在、已停用或同一能力被重复编排");
            var row=rows.getFirst(); Object state=node.getOrDefault("enabled",true); if(!(state instanceof Boolean active))throw ApiInput.invalid();
            if(!VerificationOrchestration.validRegistration((String)row.get("key"),(String)row.get("kind"),Boolean.TRUE.equals(row.get("is_locked")),(String)row.get("core_scope")))throw new ApiProblem(422,"INPUT_INVALID","能力身份或固定核心作用域无效");
            if(Boolean.TRUE.equals(row.get("is_locked")) && !active)throw new ApiProblem(422,"INPUT_INVALID","系统主干能力不可停用");
            if(active)enabled.add((String)row.get("key")); result.add(Map.of("version",version,"scope",row.get("core_scope"),"enabled",active,"parameters",object(node,"parameters")));
        }
        if(!enabled.containsAll(VerificationOrchestration.CORE))throw new ApiProblem(422,"INPUT_INVALID","模板必须包含全部固定核验主干"); return result;
    }
    private Map<String,Object> requireCapability(UUID project,UUID capability) {
        var rows=jdbc.queryForList("SELECT * FROM agent_capabilities WHERE id=? AND project_id=? FOR UPDATE",capability,project); if(rows.isEmpty())throw missing(); return rows.getFirst();
    }
    private void unique(String table,String column,UUID project,String value,String message) {
        if(jdbc.queryForObject("SELECT count(*) FROM "+table+" WHERE project_id=? AND "+column+"=?",Integer.class,project,value)>0)throw new ApiProblem(409,"STATE_CONFLICT",message);
    }
    static Map<String,Object> toolBinding(Map<String,Object> row) {
        Map<String,Object> result=new LinkedHashMap<>(); result.put("toolId",row.get("id").toString()); result.put("key",row.get("key")); result.put("type",row.get("tool_type"));
        result.put("endpointUrl",row.get("endpoint_url")); result.put("secretRef",row.get("secret_ref")); result.put("inputSchema",Json.object(row.get("input_schema").toString())); result.put("outputSchema",Json.object(row.get("output_schema").toString())); return result;
    }
    static String optional(Map<String,Object> body,String key,int max) { return body.containsKey(key)?ApiInput.text(body,key,0,max):""; }
    @SuppressWarnings("unchecked") static Map<String,Object> object(Map<String,Object> body,String key) {
        Object value=body.getOrDefault(key,Map.of()); if(!(value instanceof Map<?,?>))throw ApiInput.invalid(); return (Map<String,Object>)value;
    }
    @SuppressWarnings("unchecked") static List<Map<String,Object>> nodes(Map<String,Object> body) {
        if(!(body.get("nodes") instanceof List<?> list) || list.stream().anyMatch(value->!(value instanceof Map<?,?>)))throw ApiInput.invalid(); return (List<Map<String,Object>>)list;
    }
    private static String key(Map<String,Object> body) { String key=UnicodeText.strip(ApiInput.text(body,"key",3,96)).toLowerCase(Locale.ROOT); if(!key.matches("[a-z][a-z0-9-]{2,95}"))throw ApiInput.invalid(); return key; }
    private static String name(Map<String,Object> body) { String name=UnicodeText.strip(ApiInput.text(body,"name",1,160)); if(name.isEmpty())throw ApiInput.invalid(); return name; }
    private static ApiProblem missing() { return new ApiProblem(404,"RESOURCE_NOT_FOUND","能力、任务或模板不存在"); }
}
