import json

from devproof_agent.workflows.frozen_input import load_frozen_input


async def run_evidence_question(registry, assignment, gateway, context):
    body = await load_frozen_input(assignment, gateway, context, "read_evidence_question_input", "evidence-question-input-v1")
    await context.emit("EVIDENCE_QUESTION_INPUT_LOADED", {"contentHash": assignment["inputSnapshotRef"]["contentHash"],
        "evidenceCount": len(body["evidence"])}, context)
    return await registry.run("evidence-question-agent", json.dumps({"input": body,
        "instruction": "仅根据这些冻结证据回答问题，回答是参考信息，不能作出正式核验裁决。"},
        ensure_ascii=False), assignment, gateway, context)
