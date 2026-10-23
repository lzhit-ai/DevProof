package ai.devproof.planning;

import ai.devproof.agentjob.AgentTaskTool;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PlanningToolsConfiguration {
    @Bean AgentTaskTool readSnapshot(PlanningMaterials materials) { return bind("read_snapshot",materials); }
    @Bean AgentTaskTool searchSnapshot(PlanningMaterials materials) { return bind("search_snapshot",materials); }
    @Bean AgentTaskTool readFile(PlanningMaterials materials) { return bind("read_file",materials); }
    private AgentTaskTool bind(String key,PlanningMaterials materials) {
        return new AgentTaskTool() {
            public String key() { return key; }
            public String version() { return "v1"; }
            public Object execute(Map<String,Object> payload,Map<String,Object> arguments) { return materials.execute(key,payload,arguments); }
        };
    }
}
