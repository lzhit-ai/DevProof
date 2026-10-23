"""Export registered Agent configuration; contains code/configuration, no business data."""

import hashlib
import json
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root.parent / "agent-service/src"))
    from devproof_agent.agents.registry import DEFINITIONS, TOOL_SPECS
    from devproof_agent.agents.verification import RESULT
    from devproof_agent.agents.delivery_claims import CLAIM_OUTPUT
    from devproof_agent.agents.questions import QUESTION_OUTPUT

    agents = []
    for definition in DEFINITIONS.values():
        prompt = definition.instruction + "\n输出 JSON Schema：" + json.dumps(definition.output_schema, ensure_ascii=False)
        agents.append({
            "key": definition.key, "version": definition.version,
            "prompt": prompt, "promptHash": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "outputSchema": definition.output_schema, "tools": list(definition.tools), "delegates": list(definition.delegates),
        })
    bundle = {"schemaVersion": "agent-registry-v1", "agents": agents,
        "tools": [{"key": key, "version": "v1", "description": spec.description, "inputSchema": spec.input_schema} for key, spec in TOOL_SPECS.items()]}
    bundle["tools"].append({"key": "delegate_agent", "version": "v1", "description": "受控注册能力委派"})
    (root / "agent-registry-v1.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "schemas/verification-result-v1.json").write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **RESULT}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "schemas/delivery-claim-proposal-v1.json").write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **CLAIM_OUTPUT}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "schemas/evidence-question-result-v1.json").write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **QUESTION_OUTPUT}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Exported the actual registered Agent prompts, schemas and tool versions.")


if __name__ == "__main__":
    main()
