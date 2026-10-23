"""Read exact, authorized Java input bytes before running a model."""

import hashlib
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from devproof_agent.models import AgentError


async def load_frozen_input(assignment, gateway, context, tool_key: str, schema_name: str):
    context.budget.tool()
    frozen = await gateway.tool(tool_key, {})
    raw = frozen.get("inputJson")
    expected = assignment["inputSnapshotRef"]["contentHash"]
    if (not isinstance(raw, str) or frozen.get("contentHash") != expected
        or "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest() != expected):
        raise AgentError("INPUT_STALE", "原始输入与冻结摘要不一致")
    try:
        body = json.loads(raw)
        root = Path(os.environ.get("CONTRACT_SCHEMA_ROOT", Path(__file__).resolve().parents[4] / "contracts/schemas"))
        schema = json.loads((root / (schema_name + ".json")).read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(body)
    except (ValueError, ValidationError, OSError):
        raise AgentError("CONTRACT_INVALID", "输入或已安装 Schema 不符合版本化契约") from None
    if body["projectId"] != assignment["projectId"] or assignment["businessRef"]["id"] != assignment["inputSnapshotRef"]["id"]:
        raise AgentError("INPUT_STALE", "业务引用或项目范围不一致")
    context.budget.check()
    return body
