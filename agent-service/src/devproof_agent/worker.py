"""Pull tasks, renew leases, run Agents and submit idempotent candidates."""

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from devproof_agent.adapters.business_api import BusinessAPI, TaskGateway
from devproof_agent.adapters.openai_compatible import OpenAICompatibleModel
from devproof_agent.agents.registry import AgentRegistry
from devproof_agent.models import AgentError
from devproof_agent.runtime.core import AgentRuntime, RunContext, SharedBudget
from devproof_agent.workflows.verification import run_verification
from devproof_agent.workflows.claims import run_claim_proposal
from devproof_agent.workflows.questions import run_evidence_question

LOG = logging.getLogger(__name__)


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AgentError("CONFIG_MISSING", f"缺少配置 {name}")
    return value


async def heartbeat(gateway: TaskGateway, execution: asyncio.Task, stop: asyncio.Event):
    lease = gateway.assignment["leaseDurationSeconds"]
    deadline = time.monotonic() + lease - 2
    interval = max(2, min(15, lease // 3))
    while not stop.is_set():
        try:
            async with asyncio.timeout(max(0.1, deadline - time.monotonic())):
                response = await gateway.api.post(f"/internal/v1/agent-tasks/{gateway.assignment['taskId']}/heartbeat", gateway.base)
            if response["cancelRequested"]:
                gateway.stop_code = "RUN_CANCELLED"
                execution.cancel(); return
            deadline = time.monotonic() + response["leaseDurationSeconds"] - 2
        except AgentError as exc:
            if exc.code != "NETWORK_ERROR" or time.monotonic() >= deadline:
                gateway.stop_code = exc.code if exc.code != "NETWORK_ERROR" else "LEASE_EXPIRED"
                execution.cancel(); return
        except (TimeoutError, KeyError, TypeError):
            gateway.stop_code = "LEASE_EXPIRED"
            execution.cancel(); return
        try:
            await asyncio.wait_for(stop.wait(), timeout=min(interval, max(0.1, deadline - time.monotonic())))
        except TimeoutError:
            pass


async def execute(api: BusinessAPI, assignment: dict):
    gateway = TaskGateway(api, assignment)
    spec = assignment["budget"]
    budget = SharedBudget(time.monotonic() + spec["timeoutSeconds"], spec["maxTurns"],
        spec["maxToolCalls"], spec["maxChildAgents"], spec["maxDelegationDepth"],
        max_context_chars=int(os.environ.get("AGENT_CONTEXT_CHAR_BUDGET", "160000")))
    context = RunContext(budget, gateway.emit)
    stop = asyncio.Event()
    execution = renewal = model_client = None
    try:
        frozen = assignment["agentManifest"]["modelConfiguration"]
        credentials = await api.post(f"/internal/v1/agent-tasks/{assignment['taskId']}/model-credential", gateway.base)
        if credentials.get("modelConfigRef") != assignment["agentManifest"]["modelConfigRef"] or credentials.get("modelConfiguration") != frozen:
            raise AgentError("MODEL_CONFIG_CHANGED", "个人模型配置与任务冻结版本不一致，请重新创建任务")
        key = credentials.pop("apiKey", None)
        if not isinstance(key, str) or not key:
            raise AgentError("USER_MODEL_NOT_CONFIGURED", "任务发起用户尚未配置个人 AI 模型")
        # The adapter, headers and cookie jar belong to this task only.
        model_client = httpx.AsyncClient(follow_redirects=False)
        registry = AgentRegistry(AgentRuntime(OpenAICompatibleModel(model_client,
            base_url=frozen["baseUrl"], api_key=key, model=frozen["model"])))
        if assignment["taskKind"] == "DELIVERY_VERIFY":
            scenario = run_verification(registry, assignment, gateway, context)
            result_schema = "verification-result-v1"
        elif assignment["taskKind"] == "DELIVERY_CLAIM_PROPOSE":
            scenario = run_claim_proposal(registry, assignment, gateway, context)
            result_schema = "delivery-claim-proposal-v1"
        elif assignment["taskKind"] == "EVIDENCE_QUESTION":
            scenario = run_evidence_question(registry, assignment, gateway, context)
            result_schema = "evidence-question-result-v1"
        else:
            scenario = registry.run("planning-agent", json.dumps({
                "taskKind": assignment["taskKind"], "inputSnapshotRef": assignment["inputSnapshotRef"],
                "instruction": "先读取任务冻结输入，然后根据真实材料完成本次需求澄清或规划。",
            }, ensure_ascii=False), assignment, gateway, context)
            result_schema = "planning-result-v1"
        execution = asyncio.create_task(scenario)
        renewal = asyncio.create_task(heartbeat(gateway, execution, stop))
        async with asyncio.timeout(spec["timeoutSeconds"]):
            candidates = await execution
        encoded = json.dumps(candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        evidence = set()
        if assignment["taskKind"] == "EVIDENCE_QUESTION":
            evidence.update(assignment["allowedEvidenceIds"])
        if assignment["taskKind"] == "DELIVERY_VERIFY":
            evidence.update(item["evidenceId"] for item in candidates["findings"])
            evidence.update(value for item in candidates["challenges"] for value in item["evidenceIds"])
            evidence.update(item["evidenceId"] for item in candidates["links"])
            evidence.update(item["evidenceId"] for result in candidates["customResults"] for item in result["links"])
        body = {**gateway.base, "inputSnapshotRef": assignment["inputSnapshotRef"], "resultSchemaVersion": result_schema,
            "resultHash": "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest(), "evidenceRefs": sorted(evidence), "candidatesJson": encoded}
        for attempt in range(3):
            try:
                await api.post(f"/internal/v1/agent-tasks/{assignment['taskId']}/result", body)
                LOG.info("task_result_accepted task_id=%s attempt_id=%s", assignment["taskId"], assignment["attemptId"])
                break
            except AgentError as exc:
                if exc.code != "NETWORK_ERROR" or attempt == 2:
                    raise
                await asyncio.sleep(attempt + 1)
    except (AgentError, TimeoutError, asyncio.CancelledError, ValidationError, KeyError, TypeError, ValueError) as exc:
        interrupted = isinstance(exc, asyncio.CancelledError) and asyncio.current_task().cancelling() > 0
        code = exc.code if isinstance(exc, AgentError) else "BUDGET_EXHAUSTED" if isinstance(exc, TimeoutError) else "WORKER_INTERRUPTED" if interrupted else gateway.stop_code if isinstance(exc, asyncio.CancelledError) else "CONTRACT_INVALID"
        LOG.warning("task_execution_stopped task_id=%s code=%s", assignment["taskId"], code)
        try:
            await api.post(f"/internal/v1/agent-tasks/{assignment['taskId']}/failure", {
                **gateway.base, "errorCode": code, "messageRedacted": "执行已停止，详情见错误码和实际事件。",
                "reason": "BUDGET_EXHAUSTED" if code == "BUDGET_EXHAUSTED" else "CANCELLED" if code == "RUN_CANCELLED" else "FAILED",
            })
        except AgentError:
            LOG.warning("task_failure_not_accepted task_id=%s", assignment["taskId"])
        if interrupted:
            raise
    finally:
        stop.set()
        if execution is not None and not execution.done():
            execution.cancel()
        if execution is not None:
            await asyncio.gather(execution, return_exceptions=True)
        if renewal is not None:
            await renewal
        if model_client is not None:
            await model_client.aclose()


async def main():
    root = Path(os.environ.get("CONTRACT_SCHEMA_ROOT", Path(__file__).resolve().parents[3] / "contracts/schemas"))
    schema = json.loads((root / "task-assignment-v1.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    worker_id, token = required("WORKER_ID"), required("AGENT_SERVICE_TOKEN")
    base = required("BUSINESS_API_URL")
    poll_seconds = float(os.environ.get("AGENT_POLL_SECONDS", "3"))
    if not 1 <= poll_seconds <= 60:
        raise AgentError("CONFIG_INVALID", "AGENT_POLL_SECONDS 必须在 1 到 60 秒之间")
    async with httpx.AsyncClient(follow_redirects=False) as client:
        api = BusinessAPI(client, base_url=base, worker_id=worker_id, token=token)
        LOG.info("worker_started worker_id=%s", worker_id)
        while True:
            try:
                assignment = await api.claim()
                if assignment is not None:
                    validator.validate(assignment)
                    await execute(api, assignment)
                    continue
            except ValidationError:
                raise AgentError("CONTRACT_INVALID", "Java 任务分配不符合已锁定协议") from None
            except AgentError as exc:
                LOG.warning("worker_poll_failed code=%s", exc.code)
                if exc.code in {"WORKER_AUTH_INVALID", "WORKER_AUTH_NOT_CONFIGURED", "CONTRACT_INVALID"}:
                    raise
            await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except AgentError as exc:
        LOG.error("worker_stopped code=%s message=%s", exc.code, exc.message)
        raise SystemExit(1) from None
