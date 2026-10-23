"""Export the actual stateless compute wire types, without sample business data."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent / "agent-service/src"))
from devproof_agent.compute.types import (
    ConfigurationResponse, DocumentComputation, DocumentInspection, EmbeddingBatchRequest, EmbeddingBatchResult, NormalizedChunks,
)

for name, model in {
    "compute-configuration-v1": ConfigurationResponse,
    "document-inspection-v1": DocumentInspection,
    "document-computation-v1": DocumentComputation,
    "embedding-batch-request-v1": EmbeddingBatchRequest,
    "embedding-batch-result-v1": EmbeddingBatchResult,
    "normalized-chunks-v1": NormalizedChunks,
}.items():
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **model.model_json_schema()}
    (root / "schemas" / (name + ".json")).write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("Exported six stateless compute schemas from actual Python wire types.")
