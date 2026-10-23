package ai.devproof.agentjob;

import java.util.Map;
import java.util.UUID;

public interface AgentResultConsumer {
    boolean supports(String taskKind);
    String schemaVersion();
    void accept(Map<String, Object> task, Map<String, Object> candidates, java.util.List<UUID> evidenceRefs);
}
