package ai.devproof.agentjob;

import java.util.Map;

public interface AgentTaskTool {
    String key();
    String version();
    Object execute(Map<String,Object> taskPayload, Map<String,Object> arguments);
}
