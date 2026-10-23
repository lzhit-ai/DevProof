package ai.devproof.evidence;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class EvidenceMaterialsController {
    private final EvidenceMaterials materials;
    public EvidenceMaterialsController(EvidenceMaterials materials) { this.materials=materials; }
    @PostMapping("/api/v1/cycles/{cycle}/manual-evidence") public ResponseEntity<?> manual(@PathVariable UUID cycle,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); return response(materials.manual(cycle,actor,CommandStore.context(request,key,raw),ApiInput.text(body,"logical_name",1,255),ApiInput.text(body,"content",1,2*1024*1024)));
    }
    @PostMapping("/api/v1/cycles/{cycle}/external-evidence") public ResponseEntity<?> external(@PathVariable UUID cycle,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); String type=ApiInput.text(body,"evidence_type",1,16),sha=ApiInput.text(body,"commit_sha",40,40);
        if(!Set.of("TEST","BUILD").contains(type) || !sha.matches("[a-fA-F0-9]{40}"))throw ApiInput.invalid(); Integer exit=null;
        if(body.get("exit_code")!=null) {
            if(!(body.get("exit_code") instanceof Number number) || number.doubleValue()!=number.intValue() || number.intValue()<-255 || number.intValue()>255)throw ApiInput.invalid(); exit=number.intValue();
        }
        return response(materials.external(cycle,actor,CommandStore.context(request,key,raw),type,ApiInput.text(body,"logical_name",1,255),sha.toLowerCase(Locale.ROOT),ApiInput.text(body,"content",1,2*1024*1024),exit));
    }
    @GetMapping("/api/v1/analysis-runs/{run}/tool-executions") public List<Map<String,Object>> executions(@PathVariable UUID run,@RequestAttribute("actorId") UUID actor) { return materials.executions(run,actor); }
    @PostMapping("/api/v1/analysis-runs/{run}/tool-executions/{execution}/import-manual-evidence") public ResponseEntity<?> importResult(@PathVariable UUID run,@PathVariable UUID execution,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        return response(materials.importExecution(run,execution,actor,CommandStore.context(request,key,raw),ApiInput.text(ApiInput.object(raw),"logical_name",1,255)));
    }
    @GetMapping("/api/v1/input-snapshots/{snapshot}/evidence/{evidence}") public Map<String,Object> citation(@PathVariable UUID snapshot,@PathVariable UUID evidence,@RequestAttribute("actorId") UUID actor) { return materials.citation(snapshot,evidence,actor); }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
