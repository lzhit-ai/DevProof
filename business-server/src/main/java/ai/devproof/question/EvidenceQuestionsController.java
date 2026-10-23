package ai.devproof.question;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/input-snapshots/{snapshot}/questions")
public class EvidenceQuestionsController {
    private final EvidenceQuestions questions;
    public EvidenceQuestionsController(EvidenceQuestions questions) { this.questions=questions; }
    @PostMapping public ResponseEntity<?> ask(@PathVariable UUID snapshot,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); String question=ApiInput.text(body,"question",1,2000); var refs=ApiInput.uuids(body,"evidence_ids",20);
        if(refs.isEmpty() || UnicodeText.strip(question).isEmpty())throw ApiInput.invalid();
        var result=questions.ask(snapshot,actor,CommandStore.context(request,key,raw),question,refs); return ResponseEntity.status(result.status()).body(result.body());
    }
    @GetMapping public List<Map<String,Object>> list(@PathVariable UUID snapshot,@RequestAttribute("actorId") UUID actor) { return questions.list(snapshot,actor); }
    @GetMapping("/{id}") public Map<String,Object> get(@PathVariable UUID snapshot,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) { return questions.get(snapshot,id,actor); }
}
