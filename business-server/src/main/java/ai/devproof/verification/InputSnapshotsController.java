package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Validator;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class InputSnapshotsController {
    private final InputSnapshotLifecycle inputs;
    private final Validator validator;
    public InputSnapshotsController(InputSnapshotLifecycle inputs,Validator validator) { this.inputs=inputs; this.validator=validator; }
    public record Preparation(@NotEmpty List<@NotNull UUID> source_revision_ids) {}
    public record Formal(@NotNull @Size(max=100) List<@NotNull UUID> source_revision_ids,@NotNull UUID git_snapshot_id,
            @NotNull @Size(max=100) List<@NotNull UUID> external_evidence_ids,@NotNull @Size(max=100) List<@NotNull UUID> manual_evidence_ids) {}
    @PostMapping("/cycles/{cycleId}/input-snapshots")
    public ResponseEntity<?> preparation(@PathVariable UUID cycleId,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody byte[] raw,HttpServletRequest request) {
        Preparation input=decode(raw,Preparation.class,Map.of(),"source_revision_ids");
        return response(inputs.preparation(cycleId,actor,CommandStore.context(request,key,raw),input.source_revision_ids()));
    }
    @PostMapping("/cycles/{cycleId}/input-snapshots/formal")
    public ResponseEntity<?> formal(@PathVariable UUID cycleId,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody byte[] raw,HttpServletRequest request) {
        Formal input=decode(raw,Formal.class,Map.of("source_revision_ids",List.of(),"external_evidence_ids",List.of(),"manual_evidence_ids",List.of()),
            "source_revision_ids","git_snapshot_id","external_evidence_ids","manual_evidence_ids");
        return response(inputs.formal(cycleId,actor,CommandStore.context(request,key,raw),
            new InputSnapshotLifecycle.Selection(input.source_revision_ids(),input.git_snapshot_id(),input.external_evidence_ids(),input.manual_evidence_ids())));
    }
    @GetMapping("/input-snapshots/{snapshotId}/body")
    public Map<String,Object> frozen(@PathVariable UUID snapshotId,@RequestAttribute("actorId") UUID actor) { return inputs.frozen(snapshotId,actor); }
    private <T> T decode(byte[] raw,Class<T> type,Map<String,Object> defaults,String... fields) {
        Object parsed=Json.read(raw); if(!(parsed instanceof Map<?,?> source))throw new ApiProblem(422,"INPUT_INVALID","请求正文必须是 JSON 对象");
        Map<String,Object> values=new LinkedHashMap<>(defaults);
        for(String key:fields)if(source.containsKey(key))values.put(key,source.get(key));
        T input=Json.read(Json.write(values),type);
        if(!validator.validate(input).isEmpty())throw new ApiProblem(422,"INPUT_INVALID","快照输入不符合约束"); return input;
    }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
