package ai.devproof.delivery;

import ai.devproof.agentjob.*;
import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class DeliveryClaimTaskHandler implements AgentResultConsumer,AgentTaskObserver {
    private final DeliveryClaims claims;
    private final DeliveryClaimsStore data;
    private final BusinessOwnership owners;
    private final ModelCallAudit modelCalls;
    public DeliveryClaimTaskHandler(DeliveryClaims claims,DeliveryClaimsStore data,BusinessOwnership owners,ModelCallAudit modelCalls) { this.claims=claims; this.data=data; this.owners=owners; this.modelCalls=modelCalls; }
    public boolean supports(String kind) { return "DELIVERY_CLAIM_PROPOSE".equals(kind); }
    public String schemaVersion() { return "delivery-claim-proposal-v1"; }
    public void accept(Map<String,Object> task,Map<String,Object> candidates,List<UUID> evidence) { claims.accept(task,candidates,evidence); }
    public void status(Map<String,Object> task,String status,String code) { owners.requireJavaDeliveryClaims(); data.status((UUID)task.get("claim_proposal_run_id"),status,code); }
    public void event(Map<String,Object> task,Map<String,Object> event) {
        owners.requireJavaDeliveryClaims();
        modelCalls.record(task,event,"delivery-claim-proposer","DELIVERY_CLAIM_PROPOSAL","delivery-claim-proposer-v1","delivery-claim-proposal-v1");
    }
}
