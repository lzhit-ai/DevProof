package ai.devproof.report;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import ai.devproof.project.ProjectAccess;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/projects/{projectId}")
public class ReportController {
    private final ProjectAccess access;
    private final ReportMapper reports;
    private final PublishedBodyCache cache;
    public ReportController(ProjectAccess access, ReportMapper reports, PublishedBodyCache cache) {
        this.access = access; this.reports = reports; this.cache = cache;
    }
    @GetMapping("/report-versions")
    public List<Map<String, Object>> reports(@PathVariable UUID projectId, @RequestAttribute("actorId") UUID actorId,
            @RequestParam(name="status_filter", required=false) String status) {
        access.require(projectId, actorId); return reports.reports(projectId, status);
    }
    @GetMapping("/report-versions/{reportId}")
    public Map<String, Object> report(@PathVariable UUID projectId, @PathVariable UUID reportId, @RequestAttribute("actorId") UUID actorId) {
        access.require(projectId, actorId); return require(reports.report(projectId, reportId));
    }
    @GetMapping("/report-versions/{reportId}/content")
    public Map<String, Object> content(@PathVariable UUID projectId, @PathVariable UUID reportId, @RequestAttribute("actorId") UUID actorId) {
        Map<String, Object> projection = report(projectId, reportId, actorId);
        Map<String, Object> body = "PUBLISHED".equals(projection.get("status")) ? cache.read(projectId, reportId) : null;
        projection.put("items", body == null ? Json.read(reports.contentItems(reportId)) : body.get("items"));
        if (body != null) {
            projection.put("editorial_note",body.get("editorialNote"));
            projection.put("content_hash",body.get("reportContentHash"));
            projection.put("snapshot_hash",body.get("snapshotHash"));
            projection.put("record_type",body.get("recordType"));
            if(body.containsKey("planBaseline"))projection.put("planBaseline",body.get("planBaseline"));
        } else {
            Map<String,Object> baseline=reports.planBaseline(reportId);
            if(baseline!=null) {
                String raw=(String)baseline.get("body_json");
                if(!Json.hash(raw).equals(baseline.get("selection_hash")))throw new ApiProblem(409,"INPUT_STALE","冻结计划摘要不一致");
                projection.put("planBaseline",Map.of("selectionId",baseline.get("selection_id"),"selectionHash",baseline.get("selection_hash"),
                    "planVersionId",baseline.get("plan_version_id"),"planContentHash",baseline.get("plan_content_hash"),"body",Json.object(raw)));
            }
        }
        return projection;
    }
    @GetMapping("/published-records")
    public List<Map<String, Object>> records(@PathVariable UUID projectId, @RequestAttribute("actorId") UUID actorId) {
        access.require(projectId, actorId); return reports.records(projectId);
    }
    @GetMapping("/published-records/{recordId}")
    public Map<String, Object> record(@PathVariable UUID projectId, @PathVariable UUID recordId, @RequestAttribute("actorId") UUID actorId) {
        access.require(projectId, actorId); return require(reports.record(projectId, recordId));
    }
    private Map<String, Object> require(Map<String, Object> value) {
        if (value == null) throw new ApiProblem(404, "RESOURCE_NOT_FOUND", "报告或正式记录不存在或不属于当前项目");
        return value;
    }
}
