"""Embeddable Agent loop. No business DTO, ORM, HTTP host or concrete agent."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from devproof_agent.models import AgentError, Model, ToolSpec


@dataclass
class SharedBudget:
    deadline: float
    max_turns: int
    max_tools: int
    max_children: int
    max_depth: int
    max_context_chars: int = 160000
    turns: int = 0
    tools: int = 0
    children: int = 0

    def check(self):
        if time.monotonic() >= self.deadline:
            raise AgentError("BUDGET_EXHAUSTED", "执行时间预算已耗尽")

    def turn(self):
        self.check()
        if self.turns >= self.max_turns:
            raise AgentError("BUDGET_EXHAUSTED", "模型轮数预算已耗尽")
        self.turns += 1

    def tool(self):
        self.check()
        if self.tools >= self.max_tools:
            raise AgentError("BUDGET_EXHAUSTED", "工具调用预算已耗尽")
        self.tools += 1

    def child(self, depth: int):
        self.check()
        if depth > self.max_depth or self.children >= self.max_children:
            raise AgentError("BUDGET_EXHAUSTED", "子 Agent 数量或深度预算已耗尽")
        if self.max_turns - self.turns < 2:
            raise AgentError("DELEGATION_BUDGET_EXHAUSTED", "剩余模型轮数不足以执行子 Agent 并返回父 Agent")
        self.children += 1


EventSink = Callable[[str, dict, "RunContext"], Awaitable[None]]


@dataclass(frozen=True)
class RunContext:
    budget: SharedBudget
    emit: EventSink
    instance_id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None
    depth: int = 0


@dataclass(frozen=True)
class ExecutableTool:
    spec: ToolSpec
    execute: Callable[[dict, RunContext], Awaitable[object]]


class AgentRuntime:
    def __init__(self, model: Model):
        self.model = model

    async def run(self, *, instruction: str, task: str, tools: list[ExecutableTool],
                  output_schema: dict, context: RunContext) -> dict:
        allowed = {item.spec.name: item for item in tools}
        if len(allowed) != len(tools):
            raise AgentError("TOOL_CONFIG_INVALID", "工具名称重复")
        messages = [{"role": "system", "content": instruction}, {"role": "user", "content": task}]
        await context.emit("AGENT_STARTED", {}, context)
        try:
            while True:
                context.budget.turn()
                if len(json.dumps(messages, ensure_ascii=False)) > context.budget.max_context_chars:
                    raise AgentError("BUDGET_EXHAUSTED", "上下文字符预算已耗尽")
                remaining_turns = context.budget.max_turns - context.budget.turns + 1
                closing = remaining_turns <= (2 if context.parent_id else 1)
                notice = {"modelTurnsIncludingThisTurn": remaining_turns,
                    "toolCallsRemaining": context.budget.max_tools - context.budget.tools,
                    "childAgentsRemaining": context.budget.max_children - context.budget.children,
                    "secondsRemaining": max(0, int(context.budget.deadline - time.monotonic())),
                    "hasParentAgent": context.parent_id is not None}
                guidance = "共享执行预算：" + json.dumps(notice, ensure_ascii=False) + "。及时用已读取的依据完成结构化结果，未知项明确说明。"
                if closing:
                    guidance += "本轮必须返回最终JSON，不再调用工具；子Agent须为父Agent保留一次收尾调用。"
                request_messages = [messages[0], {"role": "system", "content": guidance}, *messages[1:]]
                started = time.monotonic()
                try:
                    response = await self.model.complete(request_messages, [] if closing else [item.spec for item in tools], context.budget.deadline - time.monotonic())
                except AgentError as exc:
                    await context.emit("MODEL_TURN_FAILED", {"latencyMs": int((time.monotonic() - started) * 1000), "errorCode": exc.code}, context)
                    raise
                messages.append(response.message)
                await context.emit("MODEL_TURN_COMPLETED", {"usage": response.usage, "latencyMs": int((time.monotonic() - started) * 1000)}, context)
                calls = response.message.get("tool_calls") or []
                if not calls:
                    try:
                        result = json.loads(response.message.get("content") or "")
                        Draft202012Validator(output_schema, format_checker=FormatChecker()).validate(result)
                    except (ValueError, TypeError, ValidationError):
                        await context.emit("MODEL_OUTPUT_REJECTED", {"errorCode": "MODEL_SCHEMA_INVALID"}, context)
                        raise AgentError("MODEL_SCHEMA_INVALID", "Agent 输出不符合场景结果协议") from None
                    await context.emit("AGENT_COMPLETED", {}, context)
                    return result
                for call in calls:
                    context.budget.tool()
                    if not isinstance(call, dict) or not isinstance(call.get("id"), str) or not isinstance(call.get("function"), dict):
                        raise AgentError("MODEL_SCHEMA_INVALID", "工具调用缺少标识或函数描述")
                    name = call["function"].get("name")
                    await context.emit("TOOL_STARTED", {"name": name, "callId": call["id"]}, context)
                    try:
                        tool = allowed.get(name)
                        if tool is None:
                            raise AgentError("TOOL_FORBIDDEN", "工具未授权")
                        arguments = json.loads(call["function"].get("arguments") or "{}")
                        Draft202012Validator(tool.spec.input_schema).validate(arguments)
                        async with asyncio.timeout(context.budget.deadline - time.monotonic()):
                            result = await tool.execute(arguments, context)
                        output = {"ok": True, "result": result}
                    except (ValueError, TypeError, ValidationError):
                        output = {"ok": False, "errorCode": "TOOL_INPUT_INVALID"}
                    except AgentError as exc:
                        if exc.code in {"BUDGET_EXHAUSTED", "LEASE_EXPIRED", "RUN_CANCELLED", "ATTEMPT_STALE", "AUTH_REVOKED"}:
                            raise
                        output = {"ok": False, "errorCode": exc.code, "message": exc.message}
                    except TimeoutError:
                        raise AgentError("BUDGET_EXHAUSTED", "工具等待超过执行预算") from None
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(output, ensure_ascii=False, allow_nan=False)})
                    event = {"name": name, "callId": call["id"], "ok": output["ok"]}
                    if not output["ok"]:
                        event["errorCode"] = output["errorCode"]
                    await context.emit("TOOL_COMPLETED", event, context)
        except asyncio.CancelledError:
            # Parent cancellation propagates through model, tool and child awaits.
            raise
