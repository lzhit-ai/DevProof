package ai.devproof.project;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects")
public class ProjectsController {
    private final ProjectManagement projects;
    public ProjectsController(ProjectManagement projects) { this.projects=projects; }
    @GetMapping public List<Map<String,Object>> list(@RequestAttribute("actorId") UUID actor) { return projects.list(actor); }
    @GetMapping("/{project}") public Map<String,Object> get(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return projects.get(project,actor); }
    @PostMapping public ResponseEntity<?> create(@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        Map<String,Object> input=ApiInput.object(raw);
        CommandStore.Result result=projects.create(actor,CommandStore.context(request,key,raw),ApiInput.text(input,"name",1,200),ApiInput.optionalText(input,"description",4000),ApiInput.optionalText(input,"repository_url",2048),ApiInput.uuids(input,"knowledge_base_ids",Integer.MAX_VALUE));
        return ResponseEntity.status(result.status()).body(result.body());
    }
    @PostMapping("/{project}/members") public ResponseEntity<?> member(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestHeader("Idempotency-Key") String key,@RequestBody byte[] raw,HttpServletRequest request) {
        Map<String,Object> input=ApiInput.object(raw);
        CommandStore.Result result=projects.addMember(project,actor,CommandStore.context(request,key,raw),ApiInput.optionalUuid(input,"user_id"),ApiInput.optionalText(input,"user_email",255),ApiInput.text(input,"role",1,32));
        return ResponseEntity.status(result.status()).body(result.body());
    }
    @DeleteMapping("/{project}") public ResponseEntity<?> delete(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,@RequestBody byte[] raw,HttpServletRequest request) {
        Map<String,Object> input=ApiInput.object(raw); String correlation=request.getHeader("X-Correlation-Id"); if(correlation==null)correlation=UUID.randomUUID().toString();
        if(correlation.length()>64)throw ApiInput.invalid(); projects.delete(project,actor,ApiInput.text(input,"confirmation_name",1,200),correlation); return ResponseEntity.noContent().build();
    }
}
