package ai.devproof.question;

import ai.devproof.agentjob.*;
import ai.devproof.infrastructure.ApiInput;
import java.util.*;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class EvidenceQuestionTool implements AgentTaskTool {
    private final AgentTaskService service;
    private final AgentTaskMapper tasks;
    private final EvidenceQuestions questions;
    public EvidenceQuestionTool(AgentTaskService service,AgentTaskMapper tasks,EvidenceQuestions questions) { this.service=service; this.tasks=tasks; this.questions=questions; }
    public String key() { return "read_evidence_question_input"; }
    public String version() { return "v1"; }
    @Transactional public Object execute(Map<String,Object> payload,Map<String,Object> arguments) {
        if(!arguments.isEmpty())throw ApiInput.invalid(); UUID id=UUID.fromString((String)payload.get("taskId"));
        var context=new AgentTaskService.Context(id,UUID.fromString((String)payload.get("attemptId")),((Number)payload.get("fencingToken")).longValue(),(String)payload.get("workerId"));
        var task=service.current(tasks.lock(id),context,true); var input=questions.input(task); service.current(task,context,true);
        return Map.of("inputJson",input.run().get("input_json"),"contentHash",input.run().get("input_hash"));
    }
}
