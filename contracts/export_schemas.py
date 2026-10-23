"""Export protocol schemas without loading application settings or a database."""

import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root.parent / "backend"))
    from app.domain.agent_contracts import (
        AgentTaskAssignment,
        AgentTaskEvent,
        AgentTaskFailure,
        AgentTaskHeartbeat,
        AgentTaskResult,
        AgentToolCall,
        ClaimProposalInput,
        EvidenceQuestionInput,
    )

    schemas = {
        "task-assignment-v1": AgentTaskAssignment,
        "task-heartbeat-v1": AgentTaskHeartbeat,
        "task-result-v1": AgentTaskResult,
        "task-failure-v1": AgentTaskFailure,
        "task-event-v1": AgentTaskEvent,
        "tool-call-v1": AgentToolCall,
        "delivery-claim-input-v1": ClaimProposalInput,
        "evidence-question-input-v1": EvidenceQuestionInput,
    }
    target = root / "schemas"
    target.mkdir(exist_ok=True)
    for name, model in schemas.items():
        schema = model.model_json_schema(by_alias=True)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:devproof:contracts:{name}"
        (target / f"{name}.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(f"Exported {len(schemas)} schemas to {target}")


if __name__ == "__main__":
    main()
