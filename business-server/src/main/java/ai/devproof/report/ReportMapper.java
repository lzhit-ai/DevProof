package ai.devproof.report;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ReportMapper {
    String REPORT_SELECT = """
        SELECT r.id,r.cycle_id,r.sequence_no,r.status,r.record_type,r.content_hash,r.version,r.snapshot_hash,
          r.editorial_note,r.submitted_at,t.id AS task_id,t.title AS task_title,t.requirement_key,t.delivery_item_id,
          u.display_name AS submitted_by_name,a.action AS latest_approval_action,a.reason AS latest_approval_reason,
          a.created_at AS latest_approval_at
        FROM report_versions r JOIN verification_cycles c ON c.id=r.cycle_id
        JOIN verification_tasks t ON t.id=c.task_id LEFT JOIN users u ON u.id=r.submitted_by
        LEFT JOIN LATERAL (SELECT * FROM approval_actions WHERE report_version_id=r.id ORDER BY created_at DESC LIMIT 1) a ON true
        WHERE t.project_id=#{projectId}
        """;
    @Select(REPORT_SELECT + " AND (CAST(#{status} AS text) IS NULL OR r.status=#{status}) ORDER BY r.submitted_at DESC NULLS LAST,r.sequence_no DESC LIMIT 100")
    List<Map<String, Object>> reports(UUID projectId, String status);
    @Select(REPORT_SELECT + " AND r.id=#{reportId}")
    Map<String, Object> report(UUID projectId, UUID reportId);

    String RECORD_SELECT = """
        SELECT p.id,t.project_id,t.id AS task_id,t.title AS task_title,t.requirement_key,t.delivery_item_id,
          p.cycle_id,p.report_version_id,r.sequence_no AS report_sequence_no,r.status AS report_status,r.snapshot_hash,
          p.record_type,p.record_no,p.record_hash,u.display_name AS published_by_name,p.published_at,
          a.action AS approval_action,a.reason AS approval_reason,approver.display_name AS approval_by_name,a.created_at AS approval_at
        FROM published_records p JOIN report_versions r ON r.id=p.report_version_id
        JOIN verification_tasks t ON t.id=p.task_id LEFT JOIN users u ON u.id=p.published_by
        LEFT JOIN LATERAL (SELECT * FROM approval_actions WHERE report_version_id=r.id ORDER BY created_at DESC LIMIT 1) a ON true
        LEFT JOIN users approver ON approver.id=a.actor_id WHERE t.project_id=#{projectId}
        """;
    @Select(RECORD_SELECT + " ORDER BY p.published_at DESC LIMIT 100")
    List<Map<String, Object>> records(UUID projectId);
    @Select(RECORD_SELECT + " AND p.id=#{recordId}")
    Map<String, Object> record(UUID projectId, UUID recordId);

    @Select("""
        SELECT b.schema_version,b.content_hash FROM published_report_bodies b
        JOIN report_versions r ON r.id=b.report_version_id JOIN published_records p ON p.report_version_id=r.id
        WHERE r.id=#{reportId} AND r.status='PUBLISHED'
        """)
    Map<String, Object> bodyMetadata(UUID reportId);
    @Select("SELECT body_json FROM published_report_bodies WHERE report_version_id=#{reportId}")
    String body(UUID reportId);

    @Select("SELECT b.selection_id,b.selection_hash,b.plan_version_id,b.plan_content_hash,p.body_json FROM report_versions r JOIN analysis_runs a ON a.id=r.run_id JOIN input_snapshot_plans b ON b.snapshot_id=a.snapshot_id JOIN cycle_plan_selections p ON p.id=b.selection_id WHERE r.id=#{reportId}")
    Map<String,Object> planBaseline(UUID reportId);

    @Select("""
        SELECT COALESCE(jsonb_agg(item ORDER BY display_order),'[]'::jsonb)::text FROM (
          SELECT ri.display_order,jsonb_build_object('id',ri.id::text,'claimText',cl.text,'result',ri.result_snapshot,
            'disposition',ri.disposition,'citations',COALESCE(citations.items,'[]'::jsonb)) AS item
          FROM report_items ri JOIN verification_results v ON v.id=ri.result_id JOIN claims cl ON cl.id=v.claim_id
          JOIN report_versions r ON r.id=ri.report_version_id JOIN analysis_runs ar ON ar.id=r.run_id
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object('id',e.id::text,'sourceType',e.source_type,'excerpt',e.excerpt_safe,'locator',e.locator)
              ORDER BY refs.ordinality) AS items
            FROM jsonb_array_elements_text(ri.citation_snapshot->'evidenceIds') WITH ORDINALITY refs(id,ordinality)
            JOIN evidence_items e ON e.id=refs.id::uuid AND e.snapshot_id=ar.snapshot_id
          ) citations ON true WHERE ri.report_version_id=#{reportId}
        ) content
        """)
    String contentItems(UUID reportId);
}
