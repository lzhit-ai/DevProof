package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.util.Map;

/** New configurations retain exact frozen bytes; existing hashes are checked without rewriting history. */
public final class OrchestrationBodies {
    private OrchestrationBodies() {}
    public static String raw(Map<String,Object> row) {
        if(row.get("raw_body") instanceof String raw) {
            if(!Json.hash(raw).equals(row.get("content_hash")))throw stale(); return raw;
        }
        Map<String,Object> body=Map.of("template",Json.object(row.get("template_json").toString()),"nodes",Json.read(row.get("nodes_json").toString()));
        String canonical=Json.canonical(body); if(Json.hash(canonical).equals(row.get("content_hash")))return canonical;
        String previous=Json.write(body); if(Json.hash(previous).equals(row.get("content_hash")))return previous;
        throw new ApiProblem(409,"ORCHESTRATION_BODY_UNAVAILABLE","历史编排缺少可核对摘要的原始正文，保留既有结构与摘要");
    }
    public static Map<String,Object> body(Map<String,Object> row) { return Json.object(raw(row)); }
    private static ApiProblem stale() { return new ApiProblem(409,"INPUT_STALE","冻结编排原始正文摘要不一致"); }
}
