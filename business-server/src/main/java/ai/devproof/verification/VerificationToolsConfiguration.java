package ai.devproof.verification;

import ai.devproof.agentjob.AgentTaskTool;
import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.context.annotation.*;

@Configuration
public class VerificationToolsConfiguration {
    @Bean AgentTaskTool readContextCandidate(CachedContextTools context) { return bind("read_context_candidate",context,false); }
    @Bean AgentTaskTool recordContextSupplement(CachedContextTools context) { return bind("record_context_supplement",context,true); }
    private AgentTaskTool bind(String key,CachedContextTools context,boolean record) {
        return new AgentTaskTool() {
            public String key() { return key; }
            public String version() { return "v1"; }
            public Object execute(Map<String,Object> payload,Map<String,Object> arguments) { return record?context.record(payload,arguments):context.read(payload,arguments); }
        };
    }
    @Bean AgentTaskTool readDeliveryInput(VerificationMaterials materials,VerificationExecutionMapper data) {
        return new AgentTaskTool() {
            public String key() { return "read_delivery_input"; }
            public String version() { return "v1"; }
            @SuppressWarnings("unchecked") public Object execute(Map<String,Object> payload,Map<String,Object> arguments) {
                if(!arguments.isEmpty())throw new ApiProblem(422,"TOOL_INPUT_INVALID","读取冻结核验输入不接收额外范围");
                Map<String,Object> ref=(Map<String,Object>)payload.get("businessRef"), input=(Map<String,Object>)payload.get("inputSnapshotRef");
                if(!"ANALYSIS_RUN".equals(ref.get("kind")) || !"VERIFICATION".equals(input.get("kind")))throw stale();
                UUID run=UUID.fromString((String)ref.get("id")); Map<String,Object> row=data.run(run);
                if(row==null || !row.get("project_id").toString().equals(payload.get("projectId")) || !row.get("snapshot_id").toString().equals(input.get("id")) || !row.get("snapshot_hash").equals(input.get("contentHash")))throw stale();
                Map<String,Object> manifest=(Map<String,Object>)payload.get("agentManifest"), configuration=(Map<String,Object>)manifest.get("businessConfigurationRef"), frozen=data.orchestration(run);
                if(configuration==null || frozen==null || !frozen.get("id").toString().equals(configuration.get("id")) || !frozen.get("content_hash").equals(configuration.get("contentHash")))throw stale();
                return materials.read(run);
            }
            private ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","工具输入不属于本次冻结运行"); }
        };
    }
}
