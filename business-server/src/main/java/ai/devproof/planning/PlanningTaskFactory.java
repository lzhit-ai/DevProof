package ai.devproof.planning;

import ai.devproof.agentjob.AgentAssignments;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class PlanningTaskFactory {
    private final AgentAssignments assignments;
    public PlanningTaskFactory(AgentAssignments assignments) { this.assignments=assignments; }
    public UUID enqueue(UUID projectId,UUID actorId,UUID runId,UUID snapshotId,String snapshotHash,Map<String,Object> repository,String kind) {
        Map<String,Object> manifest=assignments.manifest(actorId,Set.of("planning-agent","repository-explorer"),Set.of("read_snapshot","search_snapshot","read_file","delegate_agent"),null,Map.of(),Map.of());
        return assignments.enqueue(projectId,actorId,null,runId,kind,
            Map.of("kind","PLANNING","id",snapshotId.toString(),"contentHash",snapshotHash,"schemaVersion","planning-input-v1"),null,
            List.of(Map.of("repositoryId",repository.get("repositoryId"),"targetSha",repository.get("targetSha"))),List.of(),manifest,UUID.randomUUID().toString());
    }
}
