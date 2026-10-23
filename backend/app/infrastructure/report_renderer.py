import hashlib
import json

from app.domain.ports import RenderedReport, ReportRendererPort


class CanonicalJsonReportRenderer(ReportRendererPort):
    """v1 report renderer: the canonical JSON hash is the immutable report content."""

    def render(self, *, results: list[dict], editorial_note: str, dispositions: dict[str, str | None]) -> RenderedReport:
        canonical = {"results": results, "editorialNote": editorial_note, "dispositions": dispositions}
        payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return RenderedReport(content_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}")
