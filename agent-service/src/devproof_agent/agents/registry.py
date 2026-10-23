"""Registered capabilities use the runtime; the runtime never imports them."""

import json
import hashlib
from dataclasses import dataclass

from devproof_agent.agents.planning import EXPLORER_INSTRUCTION, EXPLORER_OUTPUT, PLANNER_INSTRUCTION, PLANNING_OUTPUT
from devproof_agent.agents.delivery_claims import CLAIM_INSTRUCTION, CLAIM_OUTPUT
from devproof_agent.agents.questions import QUESTION_INSTRUCTION, QUESTION_OUTPUT
from devproof_agent.agents.verification import REVIEW_INSTRUCTION, REVIEW_OUTPUT, CHALLENGE_INSTRUCTION, CHALLENGE_OUTPUT, LINK_INSTRUCTION, LINK_OUTPUT, CUSTOM_INSTRUCTION
from devproof_agent.models import AgentError, ToolSpec
from devproof_agent.runtime.core import AgentRuntime, ExecutableTool, RunContext


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    version: str
    instruction: str
    output_schema: dict
    tools: tuple[str, ...]
    delegates: tuple[str, ...] = ()


DEFINITIONS = {
    "evidence-question-agent": AgentDefinition("evidence-question-agent", "v1", QUESTION_INSTRUCTION, QUESTION_OUTPUT, ()),
    "delivery-claim-proposer": AgentDefinition("delivery-claim-proposer", "v1", CLAIM_INSTRUCTION, CLAIM_OUTPUT, ("read_claim_proposal_input",)),
    "planning-agent": AgentDefinition("planning-agent", "v1", PLANNER_INSTRUCTION, PLANNING_OUTPUT,
        ("read_snapshot", "search_snapshot", "read_file"), ("repository-explorer",)),
    "repository-explorer": AgentDefinition("repository-explorer", "v1", EXPLORER_INSTRUCTION, EXPLORER_OUTPUT,
        ("search_snapshot", "read_file")),
    "delivery-review-agent": AgentDefinition("delivery-review-agent", "v1", REVIEW_INSTRUCTION, REVIEW_OUTPUT, ()),
    "finding-challenge-agent": AgentDefinition("finding-challenge-agent", "v1", CHALLENGE_INSTRUCTION, CHALLENGE_OUTPUT, ()),
    "evidence-link-agent": AgentDefinition("evidence-link-agent", "v2", LINK_INSTRUCTION, LINK_OUTPUT, ("search_frozen_documents",)),
    "custom-evidence-agent": AgentDefinition("custom-evidence-agent", "v1", CUSTOM_INSTRUCTION, LINK_OUTPUT, ()),
}
TOOL_SPECS = {
    "read_evidence_question_input": ToolSpec("read_evidence_question_input", "读取本任务由 Java 冻结的提问与获授权证据，不允许替换快照或证据 ID。", {"type": "object", "properties": {}, "additionalProperties": False}),
    "read_claim_proposal_input": ToolSpec("read_claim_proposal_input", "读取本次主张提取任务已冻结且仍获授权的 PR 元数据与已选资料摘录。", {"type": "object", "properties": {}, "additionalProperties": False}),
    "search_frozen_documents": ToolSpec("search_frozen_documents", "检索本次任务已冻结且已授权的资料证据，返回原 Evidence ID、原摘录、定位和实际排名。", {
        "type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 2000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            "preferred_source_roles": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 255}}},
        "required": ["query"], "additionalProperties": False}),
    "record_context_supplement": ToolSpec("record_context_supplement", "保存经冻结原文复核的符号上下文，每次核验至多一轮。", {
        "type": "object", "properties": {"requests": {"type": "array", "maxItems": 20, "items": {"type": "object"}}, "contexts": {"type": "array", "maxItems": 20, "items": {"type": "object"}}, "skipped": {"type": "array", "maxItems": 20, "items": {"type": "object"}}},
        "required": ["requests", "contexts", "skipped"], "additionalProperties": False}),
    "read_delivery_input": ToolSpec("read_delivery_input", "读取本任务冻结的主张、证据、代码制品及编排版本。", {"type": "object", "properties": {}, "additionalProperties": False}),
    "read_context_candidate": ToolSpec("read_context_candidate", "读取已登记的目标 SHA 上下文候选，结果仅作 CONTEXT_ONLY。", {
        "type": "object", "properties": {"requests": {"type": "array", "maxItems": 20, "items": {"type": "object"}}}, "required": ["requests"], "additionalProperties": False}),
    "query_registered_tool": ToolSpec("query_registered_tool", "调用本次冻结能力所登记的只读工具，响应为临时材料。", {
        "type": "object", "properties": {"capabilityKey": {"type": "string"}, "toolKey": {"type": "string"}}, "required": ["capabilityKey", "toolKey"], "additionalProperties": False}),
    "read_snapshot": ToolSpec("read_snapshot", "读取本任务的真实需求、回答及冻结仓库文件索引。", {"type": "object", "properties": {}, "additionalProperties": False}),
    "search_snapshot": ToolSpec("search_snapshot", "在任务冻结的仓库文本中搜索，返回有界片段与位置。", {
        "type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 200}}, "required": ["query"], "additionalProperties": False}),
    "read_file": ToolSpec("read_file", "读取任务冻结范围内文件，每次最多请求200行。endLine超出文件末尾时返回至实际末行；响应给出实际endLine和文件总行数lineCount，引用须使用实际返回的行范围。结果只作为仓库分析上下文。", {
        "type": "object", "properties": {"path": {"type": "string", "minLength": 1}, "startLine": {"type": "integer", "minimum": 1},
            "endLine": {"type": "integer", "minimum": 1}}, "required": ["path", "startLine", "endLine"], "additionalProperties": False}),
}


class AgentRegistry:
    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime

    async def run(self, key: str, task: str, assignment: dict, gateway, context: RunContext) -> dict:
        definition = DEFINITIONS.get(key)
        granted = {(item["key"], item["version"]) for item in assignment["agentManifest"]["agents"]}
        if definition is None or (key, definition.version) not in granted:
            raise AgentError("AGENT_FORBIDDEN", "Agent 未注册或未授权")
        authorized_tools = {item["key"]: item["version"] for item in assignment["agentManifest"]["tools"]}
        executable = []
        for name in definition.tools:
            if authorized_tools.get(name) != "v1":
                raise AgentError("TOOL_FORBIDDEN", "Agent 需要的工具未授权")
            async def execute(arguments, run_context, tool_name=name):
                return await gateway.tool(tool_name, arguments)
            executable.append(ExecutableTool(TOOL_SPECS[name], execute))
        if definition.delegates:
            if authorized_tools.get("delegate_agent") != "v1":
                raise AgentError("AGENT_FORBIDDEN", "本任务未授权动态委派")
            async def delegate(arguments: dict, parent: RunContext):
                child_key = arguments["agentKey"]
                if child_key not in definition.delegates:
                    raise AgentError("AGENT_FORBIDDEN", "子 Agent 不在委派允许列表")
                parent.budget.child(parent.depth + 1)
                child = RunContext(parent.budget, parent.emit, parent_id=parent.instance_id, depth=parent.depth + 1)
                await parent.emit("AGENT_DELEGATED", {"agentKey": child_key, "childInstanceId": child.instance_id}, parent)
                return await self.run(child_key, arguments["task"], assignment, gateway, child)
            executable.append(ExecutableTool(ToolSpec("delegate_agent", "按需委派注册的专业 Agent，共享父任务权限与总预算。", {
                "type": "object", "additionalProperties": False, "required": ["agentKey", "task"], "properties": {
                    "agentKey": {"enum": list(definition.delegates)}, "task": {"type": "string", "minLength": 1, "maxLength": 12000},
                }}), delegate))
        instruction = definition.instruction + "\n输出 JSON Schema：" + json.dumps(definition.output_schema, ensure_ascii=False)
        expected_hash = "sha256:" + hashlib.sha256(instruction.encode("utf-8")).hexdigest()
        if {"key": key, "version": expected_hash} not in assignment["agentManifest"]["promptVersions"] or assignment["agentManifest"]["promptDefinitions"].get(key) != instruction:
            raise AgentError("AGENT_CONFIG_CHANGED", "Worker 的实际提示词与任务冻结版本不一致")
        async def emit(event_type, payload, instance):
            await context.emit(event_type, {"agentKey": key, **payload}, instance)
        actual_context = RunContext(context.budget, emit, context.instance_id, context.parent_id, context.depth)
        return await self.runtime.run(instruction=instruction, task=task, tools=executable,
            output_schema=definition.output_schema, context=actual_context)
