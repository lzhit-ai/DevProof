package ai.devproof.retrieval;

import ai.devproof.agentjob.AgentTaskTool;
import ai.devproof.infrastructure.ApiProblem;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DocumentSearchTools {
    @Bean AgentTaskTool searchFrozenDocuments(SnapshotSearchService search) {
        return new AgentTaskTool() {
            public String key() { return "search_frozen_documents"; }
            public String version() { return "v1"; }
            @SuppressWarnings("unchecked") public Object execute(Map<String,Object> payload,Map<String,Object> arguments) {
                var ref=(Map<String,Object>)payload.get("inputSnapshotRef");
                if(!"VERIFICATION".equals(ref.get("kind")))throw new ApiProblem(409,"INPUT_STALE","资料检索仅限当前核验任务的冻结范围");
                var query=SnapshotSearchController.query(arguments);
                return search.search(UUID.fromString((String)ref.get("id")),UUID.fromString((String)payload.get("actorId")),query.text(),query.limit(),query.preferred(),payload);
            }
        };
    }
}
