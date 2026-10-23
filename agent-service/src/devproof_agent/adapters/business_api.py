"""Task-bound Java calls. No user JWT, SQL or database credentials."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from devproof_agent.models import AgentError


class BusinessAPI:
    def __init__(self, client: httpx.AsyncClient, *, base_url: str, worker_id: str, token: str):
        self.client, self.base = client, base_url.rstrip("/")
        self.worker_id, self.token = worker_id, token

    async def post(self, path: str, body: dict):
        try:
            response = await self.client.post(self.base + path, json=body,
                headers={"Authorization": f"Bearer {self.token}"}, timeout=90 if path.startswith("/internal/v1/agent-tools/") else 15)
            if not response.is_success:
                try:
                    error = response.json()
                except ValueError:
                    error = {}
                raise AgentError(error.get("code", "BUSINESS_API_ERROR"), error.get("message", f"内部 API HTTP {response.status_code}"))
            return response.json() if response.content else None
        except httpx.RequestError:
            raise AgentError("NETWORK_ERROR", "Java 内部 API 连接失败或超时") from None

    async def claim(self):
        return await self.post("/internal/v1/agent-tasks/claim", {
            "contractVersion": "agent-task-v1", "workerId": self.worker_id,
            "executorVersion": "python-agent-v1", "taskKinds": ["PLAN_DRAFT", "PLAN_REFINE", "DELIVERY_VERIFY", "DELIVERY_CLAIM_PROPOSE", "EVIDENCE_QUESTION"],
        })


class TaskGateway:
    def __init__(self, api: BusinessAPI, assignment: dict):
        self.api, self.assignment = api, assignment
        self.sequence, self.event_lock = 0, asyncio.Lock()
        self.stop_code = "RUN_CANCELLED"
        self.base = {key: assignment[key] for key in ["contractVersion", "taskId", "attemptId", "fencingToken", "workerId", "correlationId"]}

    async def emit(self, event_type: str, payload: dict, context):
        async with self.event_lock:
            self.sequence += 1
            body = {**self.base, "eventSeq": self.sequence, "agentInstanceId": context.instance_id,
                "parentAgentInstanceId": context.parent_id, "toolCallId": None,
                "occurredAt": datetime.now(UTC).isoformat(), "eventType": event_type, "payloadRedacted": payload}
            await self.api.post(f"/internal/v1/agent-tasks/{self.assignment['taskId']}/events", body)

    async def tool(self, name: str, arguments: dict):
        return await self.api.post(f"/internal/v1/agent-tools/{name}/execute", {
            **self.base, "toolCallId": str(uuid4()), "tool": {"key": name, "version": "v1"},
            "inputSnapshotRef": self.assignment["inputSnapshotRef"], "arguments": arguments,
        })
