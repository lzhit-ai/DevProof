"""Materialize publication-time content; never reconstruct historical bodies."""

import hashlib
import json

from app.infrastructure.persistence.models import PublishedReportBody


def freeze_published_body(session, *, report, project_id, actor_id) -> None:
    from app.application.services.report_service import get_report_content

    content = get_report_content(session, project_id=project_id, report_id=report.id, actor_id=actor_id)
    body = {
        "schemaVersion": "published-report-body-v1",
        "reportVersionId": str(report.id),
        "reportContentHash": report.content_hash,
        "snapshotHash": report.snapshot_hash,
        "recordType": report.record_type,
        "editorialNote": report.editorial_note,
        "items": content["items"],
    }
    baseline = content.get("planBaseline")
    if baseline:
        body["schemaVersion"] = "published-report-body-v2"
        body["planBaseline"] = baseline
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    session.add(PublishedReportBody(
        report_version_id=report.id,
        schema_version=body["schemaVersion"],
        content_hash=f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}",
        body_json=encoded,
    ))
