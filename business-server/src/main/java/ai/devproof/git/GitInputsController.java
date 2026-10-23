package ai.devproof.git;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class GitInputsController {
    private final GitInputs inputs;
    public GitInputsController(GitInputs inputs) { this.inputs=inputs; }
    @GetMapping("/api/v1/projects/{project}/git-repositories") public List<Map<String,Object>> repositories(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return inputs.repositories(project,actor); }
    @PostMapping("/api/v1/projects/{project}/git-repositories") public ResponseEntity<?> register(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); return response(inputs.register(project,actor,CommandStore.context(request,key,raw),ApiInput.text(body,"display_url",8,2000),ApiInput.optionalText(body,"credential_ref",160)));
    }
    @PostMapping("/api/v1/cycles/{cycle}/git-snapshots") public ResponseEntity<?> capture(@PathVariable UUID cycle,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        var body=ApiInput.object(raw); String base=ref(body,"base_ref"),target=ref(body,"target_ref"),mode=ApiInput.text(body,"diff_mode",1,16);
        if(!Set.of("TWO_DOT","THREE_DOT").contains(mode))throw ApiInput.invalid();
        return response(inputs.capture(cycle,ApiInput.uuid(body.get("repository_id")),actor,CommandStore.context(request,key,raw),new GitComputation.Range(base,target,mode,paths(body,"include_paths"),paths(body,"exclude_paths"))));
    }
    @GetMapping("/api/v1/git-snapshots/{snapshot}/diff") public Map<String,Object> diff(@PathVariable UUID snapshot,@RequestAttribute("actorId") UUID actor) { return inputs.diff(snapshot,actor); }
    private static String ref(Map<String,Object> body,String key) {
        String value=ApiInput.text(body,key,1,255);
        if(value.startsWith("-") || value.codePoints().anyMatch(c->c<32))throw new ApiProblem(422,"GIT_REF_INVALID","请指定有效的分支、标签或提交表达式"); return value;
    }
    private static List<String> paths(Map<String,Object> body,String key) {
        if(!body.containsKey(key))return List.of();
        if(!(body.get(key) instanceof List<?> values) || values.size()>100)throw ApiInput.invalid();
        return values.stream().map(raw->{
            if(!(raw instanceof String value) || value.isEmpty() || value.codePointCount(0,value.length())>1000 || value.indexOf('\0')>=0 || value.indexOf('\n')>=0 || value.indexOf('\r')>=0)throw ApiInput.invalid(); return (String)raw;
        }).toList();
    }
    private ResponseEntity<?> response(CommandStore.Result result) { return ResponseEntity.status(result.status()).body(result.body()); }
}
