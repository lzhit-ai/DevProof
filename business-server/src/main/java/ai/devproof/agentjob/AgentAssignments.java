package ai.devproof.agentjob;

import ai.devproof.infrastructure.*;
import ai.devproof.modelsettings.UserModelSettings;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AgentAssignments {
    private final AgentTaskMapper tasks;
    private final Map<String,Object> registry;
    private final UserModelSettings models;
    private final Map<String,Object> budget;
    private final int maxAttempts;
    public AgentAssignments(AgentTaskMapper tasks,UserModelSettings models,@Value("${devproof.agent-timeout-seconds:300}") int timeout,
            @Value("${devproof.agent-max-turns:12}") int turns,@Value("${devproof.agent-max-tool-calls:30}") int tools,
            @Value("${devproof.agent-max-children:2}") int children,@Value("${devproof.agent-max-depth:2}") int depth,@Value("${devproof.agent-max-attempts:3}") int attempts) {
        this.tasks=tasks; this.models=models; this.maxAttempts=attempts;
        if(timeout<1 || turns<1 || tools<0 || children<0 || depth<0 || attempts<1)throw new IllegalArgumentException("Invalid Agent budgets");
        budget=Map.of("timeoutSeconds",timeout,"maxTurns",turns,"maxToolCalls",tools,"maxChildAgents",children,"maxDelegationDepth",depth);
        try(var stream=getClass().getResourceAsStream("/contracts/agent-registry-v1.json")) {
            if(stream==null)throw new IllegalStateException("Agent registry resource missing");
            registry=Json.object(new String(stream.readAllBytes(),StandardCharsets.UTF_8));
        } catch(java.io.IOException e) { throw new IllegalStateException("Agent registry unreadable",e); }
    }
    @SuppressWarnings("unchecked")
    public Map<String,Object> manifest(UUID actor,Set<String> agentKeys,Set<String> toolKeys,Map<String,Object> configurationRef,Map<String,String> registeredPrompts,Map<String,Object> executionConfiguration) {
        UserModelSettings.Binding binding=models.freeze(actor);
        List<Map<String,Object>> agents=new ArrayList<>(), tools=new ArrayList<>(), versions=new ArrayList<>(); Map<String,String> prompts=new LinkedHashMap<>();
        for(Map<String,Object> definition:(List<Map<String,Object>>)registry.get("agents"))if(agentKeys.contains(definition.get("key"))) {
            agents.add(Map.of("key",definition.get("key"),"version",definition.get("version")));
            prompts.put((String)definition.get("key"),(String)definition.get("prompt")); versions.add(Map.of("key",definition.get("key"),"version",definition.get("promptHash")));
        }
        for(Map<String,Object> definition:(List<Map<String,Object>>)registry.get("tools"))if(toolKeys.contains(definition.get("key")))tools.add(Map.of("key",definition.get("key"),"version",definition.get("version")));
        if(agents.size()!=agentKeys.size() || tools.size()!=toolKeys.size())throw new ApiProblem(503,"AGENT_CONFIG_MISSING","服务端可执行注册表未包含所需能力");
        registeredPrompts.forEach((key,prompt)->{prompts.put("custom:"+key,prompt); versions.add(Map.of("key","custom:"+key,"version",Json.hash(prompt)));});
        Map<String,Object> result=new LinkedHashMap<>(); result.put("id",UUID.randomUUID().toString()); result.put("agents",agents); result.put("tools",tools);
        result.put("promptVersions",versions); result.put("promptDefinitions",prompts); result.put("modelConfiguration",binding.configuration()); result.put("modelConfigRef",binding.reference());
        if(configurationRef!=null)result.put("businessConfigurationRef",configurationRef);
        result.put("executionConfiguration",executionConfiguration);
        result.put("contentHash",Json.hash(Json.write(result))); return result;
    }
    public UUID enqueue(UUID project,UUID actor,UUID run,UUID planning,String kind,Map<String,Object> input,Map<String,Object> plan,List<Map<String,Object>> repositories,List<String> evidence,Map<String,Object> manifest,String correlation) {
        return enqueue(project,actor,run,planning,null,null,kind,input,plan,repositories,evidence,manifest,correlation);
    }
    public UUID enqueueClaim(UUID project,UUID actor,UUID proposal,Map<String,Object> input,Map<String,Object> manifest,String correlation) {
        return enqueue(project,actor,null,null,proposal,null,"DELIVERY_CLAIM_PROPOSE",input,null,List.of(),List.of(),manifest,correlation);
    }
    public UUID enqueueQuestion(UUID project,UUID actor,UUID question,Map<String,Object> input,List<String> evidence,Map<String,Object> manifest,String correlation) {
        return enqueue(project,actor,null,null,null,question,"EVIDENCE_QUESTION",input,null,List.of(),evidence,manifest,correlation);
    }
    private UUID enqueue(UUID project,UUID actor,UUID run,UUID planning,UUID claim,UUID question,String kind,Map<String,Object> input,Map<String,Object> plan,List<Map<String,Object>> repositories,List<String> evidence,Map<String,Object> manifest,String correlation) {
        String referenceKind=question!=null?"EVIDENCE_QUESTION_RUN":claim!=null?"CLAIM_PROPOSAL_RUN":run!=null?"ANALYSIS_RUN":"PLANNING_RUN";
        UUID reference=question!=null?question:claim!=null?claim:run!=null?run:planning;
        Map<String,Object> payload=new LinkedHashMap<>(); payload.put("businessRef",Map.of("kind",referenceKind,"id",reference.toString()));
        payload.put("inputSnapshotRef",input); payload.put("planVersionRef",plan); payload.put("repositoryRefs",repositories); payload.put("allowedEvidenceIds",evidence);
        payload.put("agentManifest",manifest); payload.put("budget",budget); payload.put("correlationId",correlation);
        UUID id=UUID.randomUUID(); tasks.enqueue(id,project,actor,run,planning,claim,question,kind,"python-agent-v1",Json.write(payload),maxAttempts); return id;
    }
}
