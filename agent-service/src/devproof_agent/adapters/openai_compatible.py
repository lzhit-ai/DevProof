"""Real HTTP model adapter; unavailable services return explicit failures."""

import httpx
from urllib.parse import urlparse

from devproof_agent.models import AgentError, Completion, ToolSpec


class OpenAICompatibleModel:
    def __init__(self, client: httpx.AsyncClient, *, base_url: str, api_key: str, model: str):
        if not base_url.startswith(("https://", "http://")) or not api_key or not model:
            raise AgentError("MODEL_NOT_CONFIGURED", "模型地址、名称和凭据必须配置")
        self.client, self.endpoint = client, base_url.rstrip("/") + "/chat/completions"
        self.api_key, self.model = api_key, model
        self.host = urlparse(base_url).hostname

    async def complete(self, messages: list[dict], tools: list[ToolSpec], timeout: float) -> Completion:
        body = {"model": self.model, "messages": messages, "temperature": 0}
        # The catalog uses non-thinking Chat Completions for a uniform tool loop.
        if self.host == "api.deepseek.com" and self.model in ("deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
            body["thinking"] = {"type": "disabled"}
        elif self.host == "dashscope.aliyuncs.com" and self.model in ("qwen-plus", "qwen-flash"):
            body["enable_thinking"] = False
        elif self.host == "api.moonshot.cn" and self.model == "kimi-k2.6":
            body.update(thinking={"type": "disabled"}, temperature=0.6)
        elif self.host == "open.bigmodel.cn" and self.model == "glm-4.7":
            body["thinking"] = {"type": "disabled"}
        if tools:
            body.update(tools=[item.wire() for item in tools], tool_choice="auto")
        try:
            response = await self.client.post(self.endpoint, json=body,
                headers={"Authorization": f"Bearer {self.api_key}"}, timeout=min(timeout, 120))
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise ValueError("Invalid assistant message")
            if message.get("tool_calls") is not None and not isinstance(message["tool_calls"], list):
                raise ValueError("Invalid tool calls")
            # Retain only protocol fields, not provider-specific hidden content.
            return Completion({key: message[key] for key in ("role", "content", "tool_calls") if key in message}, data.get("usage") or {})
        except httpx.HTTPStatusError as exc:
            code = "MODEL_RATE_LIMITED" if exc.response.status_code == 429 else "MODEL_UNAVAILABLE" if exc.response.status_code >= 500 else "MODEL_REQUEST_INVALID"
            raise AgentError(code, f"模型调用失败（HTTP {exc.response.status_code}）") from None
        except httpx.RequestError:
            raise AgentError("MODEL_UNAVAILABLE", "模型请求超时或连接失败") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise AgentError("MODEL_SCHEMA_INVALID", "模型未返回有效的消息协议") from None
