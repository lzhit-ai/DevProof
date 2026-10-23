"""Load the actual authorized input before any claim-generation model turn."""

import json

from devproof_agent.workflows.frozen_input import load_frozen_input


async def run_claim_proposal(registry, assignment, gateway, context):
    body = await load_frozen_input(assignment, gateway, context, "read_claim_proposal_input", "delivery-claim-input-v1")
    await context.emit("CLAIM_INPUT_LOADED", {"contentHash": assignment["inputSnapshotRef"]["contentHash"],
        "documentCount": len(body["documents"])}, context)
    return await registry.run("delivery-claim-proposer", json.dumps({
        "inputSnapshotRef": assignment["inputSnapshotRef"], "input": body,
        "instruction": "根据已经读取并校验的冻结材料提取候选交付主张。",
    }, ensure_ascii=False), assignment, gateway, context)
