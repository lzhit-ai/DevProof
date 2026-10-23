package ai.devproof.knowledge;

import ai.devproof.infrastructure.*;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/projects/{project}/sources")
public class SourcesController {
    private final SourceStore sources;
    private final ComputeClient compute;
    private final ControlledArtifacts artifacts;
    private final int sourceMax,textMax;
    public SourcesController(SourceStore sources,ComputeClient compute,ControlledArtifacts artifacts,
        @Value("${SOURCE_MAX_BYTES:104857600}") int sourceMax,@Value("${COMPUTE_RESULT_MAX_BYTES:268435456}") int textMax) {
        if(sourceMax<1048576 || sourceMax>524288000)throw new IllegalArgumentException("Invalid source size");
        this.sources=sources; this.compute=compute; this.artifacts=artifacts; this.sourceMax=sourceMax; this.textMax=textMax;
    }
    @GetMapping public List<Map<String,Object>> list(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor) { return sources.list(project,actor); }
    @GetMapping("/{id}") public Map<String,Object> content(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) {
        var source=sources.readable(project,id,actor); String location=(String)source.get("extracted_artifact_uri");
        if(location==null)throw new ApiProblem(409,"SOURCE_NOT_READY","资料尚未提取出可阅读内容");
        var result=KnowledgeViews.fields(source,"media_type","logical_name","original_filename");
        result.put("content",artifacts.text(location,textMax,(String)source.get("normalized_text_hash")));
        result.put("locator_summary",KnowledgeViews.object(source.get("extraction_metadata"))); return result;
    }
    @GetMapping("/{id}/download") public ResponseEntity<byte[]> download(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) {
        var source=sources.readable(project,id,actor);
        return ResponseEntity.ok().contentType(MediaType.parseMediaType((String)source.get("media_type")))
            .header(HttpHeaders.CONTENT_DISPOSITION,ContentDisposition.attachment().filename((String)source.get("original_filename"),StandardCharsets.UTF_8).build().toString())
            .body(artifacts.read((String)source.get("artifact_uri"),sourceMax,(String)source.get("content_hash")));
    }
    @GetMapping("/{id}/chunks") public List<Map<String,Object>> chunks(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor) { return sources.chunks(project,id,actor); }
    @DeleteMapping("/{id}") public ResponseEntity<Void> delete(@PathVariable UUID project,@PathVariable UUID id,@RequestAttribute("actorId") UUID actor,HttpServletRequest request) {
        sources.delete(project,id,actor,CommandStore.context(request,null,null).correlationId()); return ResponseEntity.noContent().build();
    }
    @PostMapping(consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> upload(@PathVariable UUID project,@RequestAttribute("actorId") UUID actor,
        @RequestHeader("Idempotency-Key") String key,@RequestPart("file") MultipartFile file,
        @RequestParam("source_role") String role,@RequestParam("logical_name") String name,
        @RequestParam(value="knowledge_base_id",required=false) UUID base,
        @RequestParam(value="force_ocr",defaultValue="false") boolean forceOcr,HttpServletRequest request) {
        sources.authorizeUpload(project,actor,base);
        if(file.getSize()>sourceMax)throw new ApiProblem(413,"SOURCE_TOO_LARGE","单份资料超过配置的上传上限");
        ApiInput.text(Map.of("value",role),"value",1,64); ApiInput.text(Map.of("value",name),"value",1,255);
        String filename=normalizeFilename(file.getOriginalFilename()==null || file.getOriginalFilename().isEmpty()?name:file.getOriginalFilename());
        ApiInput.text(Map.of("value",filename),"value",1,255);
        byte[] bytes;
        try(var input=file.getInputStream()) { bytes=input.readNBytes(sourceMax+1); }
        catch(IOException e) { throw new ApiProblem(422,"SOURCE_UPLOAD_UNREADABLE","上传文件无法读取"); }
        if(bytes.length>sourceMax)throw new ApiProblem(413,"SOURCE_TOO_LARGE","单份资料超过配置的上传上限");
        // Multipart boundaries vary across retries; the command identity includes all fields and exact file bytes' hash.
        Map<String,Object> identity=new LinkedHashMap<>(); identity.put("sourceRole",role); identity.put("logicalName",name);
        identity.put("filename",filename); identity.put("knowledgeBaseId",base); identity.put("forceOcr",forceOcr); identity.put("contentHash",Json.hash(bytes));
        var command=CommandStore.context(request,key,Json.canonical(identity).getBytes(StandardCharsets.UTF_8));
        var replay=sources.preflight(project,actor,base,command); if(replay!=null)return ResponseEntity.status(replay.status()).body(replay.body());
        var inspection=compute.inspect(bytes,filename); var configuration=compute.configuration();
        var result=sources.upload(project,actor,base,role,name,filename,forceOcr,bytes,command,inspection,configuration);
        return ResponseEntity.status(result.status()).body(result.body());
    }
    private static String normalizeFilename(String raw) {
        String name=raw;
        if(raw.codePoints().allMatch(code->code<=255))try {
            name=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(raw.getBytes(StandardCharsets.ISO_8859_1))).toString();
        } catch(CharacterCodingException ignored) {}
        name=name.substring(Math.max(name.lastIndexOf('/'),name.lastIndexOf('\\'))+1);
        if(name.indexOf('\r')>=0 || name.indexOf('\n')>=0 || name.indexOf('\0')>=0)throw ApiInput.invalid(); return name;
    }
}
