package ai.devproof.question;

import ai.devproof.agentjob.*;
import ai.devproof.infrastructure.BusinessOwnership;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class EvidenceQuestionTaskHandler implements AgentResultConsumer,AgentTaskObserver {
    private final EvidenceQuestions questions;
    private final EvidenceQuestionStore data;
    private final BusinessOwnership owners;
    private final ModelCallAudit modelCalls;
    public EvidenceQuestionTaskHandler(EvidenceQuestions questions,EvidenceQuestionStore data,BusinessOwnership owners,ModelCallAudit modelCalls) { this.questions=questions; this.data=data; this.owners=owners; this.modelCalls=modelCalls; }
    public boolean supports(String kind) { return "EVIDENCE_QUESTION".equals(kind); }
    public String schemaVersion() { return "evidence-question-result-v1"; }
    public void accept(Map<String,Object> task,Map<String,Object> result,List<UUID> refs) { questions.accept(task,result,refs); }
    public void status(Map<String,Object> task,String status,String code) { owners.requireJavaEvidenceQuestions(); data.status((UUID)task.get("question_run_id"),status,code); }
    public void event(Map<String,Object> task,Map<String,Object> event) { owners.requireJavaEvidenceQuestions(); modelCalls.record(task,event,"evidence-question-agent","EVIDENCE_QA","evidence-question-agent-v1","evidence-question-result-v1"); }
}
