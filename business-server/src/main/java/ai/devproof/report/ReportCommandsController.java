package ai.devproof.report;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Validator;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class ReportCommandsController {
    private final ReportLifecycle reports;
    private final Validator validator;
    public ReportCommandsController(ReportLifecycle reports,Validator validator) { this.reports=reports; this.validator=validator; }
    public record Edit(@Min(1) int expected_version,@NotNull @Size(max=8000) String editorial_note,@NotNull @Size(max=500) Map<UUID,String> item_dispositions) {}
    public record Approval(@NotNull @Size(min=1,max=4000) String reason) {}
    public record Decision(@NotNull String decision,@NotNull @Size(max=2000) String note) {}
    @PostMapping("/cycles/{cycleId}/reports/from-run/{runId}")
    public ResponseEntity<?> draft(@PathVariable UUID cycleId,@PathVariable UUID runId,@RequestAttribute("actorId") UUID actor,
            @RequestHeader("Idempotency-Key") String key,@RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(reports.create(cycleId,runId,actor,context(request,key,raw)));
    }
    @PutMapping("/report-versions/{id}")
    public ResponseEntity<?> edit(@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody byte[] raw,HttpServletRequest request) {
        Edit input=input(raw,Edit.class,Map.of("editorial_note","","item_dispositions",Map.of()),"expected_version","editorial_note","item_dispositions");
        return response(reports.edit(id,actor,context(request,key,raw),input.expected_version(),input.editorial_note(),input.item_dispositions()));
    }
    @PostMapping("/report-versions/{id}/submit")
    public ResponseEntity<?> submit(@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(reports.submit(id,actor,context(request,key,raw)));
    }
    @PostMapping("/report-versions/{id}/approve")
    public ResponseEntity<?> approve(@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody byte[] raw,HttpServletRequest request) { return review(id,actor,key,raw,request,"APPROVED"); }
    @PostMapping("/report-versions/{id}/reject")
    public ResponseEntity<?> reject(@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody byte[] raw,HttpServletRequest request) { return review(id,actor,key,raw,request,"REJECTED"); }
    @PostMapping("/report-versions/{id}/request-changes")
    public ResponseEntity<?> changes(@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody byte[] raw,HttpServletRequest request) { return review(id,actor,key,raw,request,"CHANGES_REQUESTED"); }
    private ResponseEntity<?> review(UUID id,UUID actor,String key,byte[] raw,HttpServletRequest request,String action) {
        Approval input=input(raw,Approval.class,Map.of(),"reason");
        return response(reports.review(id,actor,context(request,key,raw),action,input.reason()));
    }
    @PostMapping("/report-versions/{id}/publish")
    public ResponseEntity<?> publish(@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,
            @RequestBody(required=false) byte[] raw,HttpServletRequest request) {
        return response(reports.publish(id,actor,context(request,key,raw)));
    }
    @PostMapping("/analysis-runs/{runId}/results/{resultId}/human-decisions")
    public ResponseEntity<?> decide(@PathVariable UUID runId,@PathVariable UUID resultId,@RequestAttribute("actorId") UUID actor,
            @RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        Decision input=input(raw,Decision.class,Map.of("note",""),"decision","note");
        return response(reports.decide(runId,resultId,actor,context(request,key,raw),input.decision(),input.note()));
    }
    private <T> T input(byte[] raw,Class<T> type,Map<String,Object> defaults,String... fields) {
        Object parsed=Json.read(raw);
        if(!(parsed instanceof Map<?,?> source))throw new ApiProblem(422,"INPUT_INVALID","请求正文必须是 JSON 对象");
        Map<String,Object> values=new LinkedHashMap<>(defaults);
        for(String field:fields)if(source.containsKey(field))values.put(field,source.get(field));
        for(String field:List.of("editorial_note","reason","decision","note"))
            if(values.containsKey(field) && !(values.get(field) instanceof String))throw new ApiProblem(422,"INPUT_INVALID","文本字段类型无效");
        if(values.get("item_dispositions") instanceof Map<?,?> dispositions)
            for(Object value:dispositions.values())if(value!=null && !(value instanceof String))throw new ApiProblem(422,"INPUT_INVALID","处置说明必须是文本或空值");
        T input=Json.read(Json.write(values),type);
        if(!validator.validate(input).isEmpty())throw new ApiProblem(422,"INPUT_INVALID","请求参数不符合约束");
        return input;
    }
    private CommandStore.Context context(HttpServletRequest request,String key,byte[] raw) {
        return CommandStore.context(request,key,raw);
    }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
