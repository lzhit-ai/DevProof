package ai.devproof.agentjob;

import java.util.Map;

/** Business projections join the task transaction; executors never set business states. */
public interface AgentTaskObserver {
    boolean supports(String kind);
    void status(Map<String,Object> task,String status,String errorCode);
    void event(Map<String,Object> task,Map<String,Object> event);
}
