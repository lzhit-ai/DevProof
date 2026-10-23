package ai.devproof.delivery;

import ai.devproof.agentjob.*;
import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class DeliveryClaimTools implements AgentTaskTool {
    private final AgentTaskService service;
    private final AgentTaskMapper tasks;
    private final DeliveryClaims claims;
    public DeliveryClaimTools(AgentTaskService service,AgentTaskMapper tasks,DeliveryClaims claims) { this.service=service; this.tasks=tasks; this.claims=claims; }
    public String key() { return "read_claim_proposal_input"; }
    public String version() { return "v1"; }
    @Transactional public Object execute(Map<String,Object> payload,Map<String,Object> arguments) {
        if(!arguments.isEmpty())throw ApiInput.invalid(); UUID id=UUID.fromString((String)payload.get("taskId"));
        var context=new AgentTaskService.Context(id,UUID.fromString((String)payload.get("attemptId")),((Number)payload.get("fencingToken")).longValue(),(String)payload.get("workerId"));
        var task=service.current(tasks.lock(id),context,true); var input=claims.input(task);
        service.current(task,context,true);
        return Map.of("inputJson",input.run().get("input_json"),"contentHash",input.run().get("input_hash"));
    }
}
