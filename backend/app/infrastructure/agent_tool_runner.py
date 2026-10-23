"""Runtime for frozen, administrator-authorized read-only Agent tools."""

import hashlib
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.config import Settings
from app.domain.errors import DomainError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: N802
        return None


@dataclass(frozen=True)
class HttpToolResult:
    content_hash: str
    content: str
    excerpt: str
    locator: dict


def _validated_endpoint(endpoint_url: object, settings: Settings) -> tuple[str, str]:
    if not isinstance(endpoint_url, str):
        raise DomainError("TOOL_CONFIG_INVALID", "冻结的 HTTP 工具缺少端点配置")
    parsed = urlparse(endpoint_url)
    host = parsed.hostname.lower() if parsed.hostname else ""
    try:
        valid_port = parsed.port in {None, 443}
    except ValueError as exc:
        raise DomainError("TOOL_CONFIG_INVALID", "冻结的 HTTP 工具端口无效") from exc
    allowed_hosts = {item.strip().lower() for item in settings.agent_tool_allowed_hosts if item.strip()}
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not valid_port
        or host not in allowed_hosts
    ):
        raise DomainError("TOOL_CONFIG_INVALID", "冻结的 HTTP 工具不在服务端白名单内")
    return endpoint_url, host


def execute_http_query(
    tool: dict,
    *,
    analysis_run_id: str,
    input_snapshot_id: str,
    capability_key: str,
    settings: Settings,
) -> HttpToolResult:
    """Perform one bounded GET request. Model output never controls the URL or query values."""
    endpoint_url, host = _validated_endpoint(tool.get("endpointUrl"), settings)
    parsed = urlparse(endpoint_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "analysisRunId": analysis_run_id,
            "inputSnapshotId": input_snapshot_id,
            "capabilityKey": capability_key,
        }
    )
    target_url = urlunparse(parsed._replace(query=urlencode(query)))
    headers = {"Accept": "application/json, text/plain;q=0.9", "User-Agent": "DevProof-AgentTool/1.0"}
    secret_ref = tool.get("secretRef")
    if secret_ref:
        if not isinstance(secret_ref, str):
            raise DomainError("TOOL_CONFIG_INVALID", "冻结的工具密钥引用无效")
        secret = os.environ.get(secret_ref)
        if not secret:
            raise DomainError("TOOL_SECRET_UNAVAILABLE", "服务端未配置该工具所需密钥")
        headers["Authorization"] = f"Bearer {secret}"
    request = Request(target_url, headers=headers, method="GET")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=settings.agent_tool_timeout_seconds) as response:
            status = response.getcode()
            content_type = response.headers.get_content_type()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > settings.agent_tool_response_limit_bytes:
                raise DomainError("TOOL_RESPONSE_TOO_LARGE", "工具响应超过允许大小")
            raw = response.read(settings.agent_tool_response_limit_bytes + 1)
        if len(raw) > settings.agent_tool_response_limit_bytes:
            raise DomainError("TOOL_RESPONSE_TOO_LARGE", "工具响应超过允许大小")
        if status < 200 or status >= 300:
            raise DomainError("TOOL_UNAVAILABLE", f"工具返回 HTTP {status}")
        if content_type == "application/json":
            content = json.dumps(json.loads(raw.decode("utf-8")), ensure_ascii=False, sort_keys=True)
        elif content_type == "text/plain":
            content = raw.decode("utf-8")
        else:
            raise DomainError("TOOL_RESPONSE_INVALID", "工具仅允许返回 JSON 或纯文本")
    except DomainError:
        raise
    except UnicodeDecodeError as exc:
        raise DomainError("TOOL_RESPONSE_INVALID", "工具响应不是 UTF-8 文本") from exc
    except json.JSONDecodeError as exc:
        raise DomainError("TOOL_RESPONSE_INVALID", "工具响应不是有效 JSON") from exc
    except HTTPError as exc:
        raise DomainError("TOOL_UNAVAILABLE", f"工具返回 HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise DomainError("TOOL_UNAVAILABLE", "工具当前不可用") from exc
    # A temporary execution is still an immutable artifact.  Its hash is the
    # exact saved response, not a hash of a URL that must never be exposed as
    # formal evidence metadata.
    content_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
    return HttpToolResult(
        content_hash=content_hash,
        content=content,
        excerpt=content[:12_000],
        locator={"toolKey": tool.get("key"), "host": host, "responseType": content_type, "statusCode": status},
    )
