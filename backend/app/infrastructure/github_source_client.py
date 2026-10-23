"""Bounded, read-only GitHub source client for project facts, not Agent tool evidence."""

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.config import Settings
from app.domain.errors import DomainError
from app.infrastructure.credential_resolver import resolve_environment_secret


_GITHUB_API_BASE_URL = "https://api.github.com"
_MAX_PAGES = 50


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: N802
        return None


class GitHubPaginationError(DomainError):
    """A bounded sync error with a safe resume/failure location, never request credentials."""

    def __init__(self, *, cause: DomainError, page_count: int, continuation_cursor: dict[str, str]) -> None:
        self.page_count = page_count
        self.continuation_cursor = continuation_cursor
        super().__init__(cause.code, cause.message)


@dataclass(frozen=True)
class GitHubSyncPayload:
    issues: list[dict]
    pull_requests: list[dict]
    milestones: list[dict]
    truncated: bool
    page_count: int
    continuation_cursor: dict


@dataclass(frozen=True)
class _PaginatedPayload:
    items: list[dict]
    truncated: bool
    page_count: int
    continuation_cursor: dict


def _safe_api_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com" or parsed.path not in {"", "/"}:
        raise DomainError("SOURCE_CONNECTION_INVALID", "GitHub 来源仅允许使用 https://api.github.com")
    return _GITHUB_API_BASE_URL


class GitHubSourceClient:
    def __init__(self, *, repository_slug: str, api_base_url: str, secret_ref: str | None, settings: Settings) -> None:
        self._repository_slug = repository_slug
        self._api_base_url = _safe_api_base_url(api_base_url)
        self._secret_ref = secret_ref
        self._settings = settings

    def fetch(self) -> GitHubSyncPayload:
        try:
            issues = self._list_paginated(f"/repos/{self._repository_slug}/issues", {"state": "all"})
        except GitHubPaginationError as exc:
            exc.continuation_cursor = {"issues": exc.continuation_cursor}
            raise
        try:
            pull_requests = self._list_paginated(f"/repos/{self._repository_slug}/pulls", {"state": "all"})
        except GitHubPaginationError as exc:
            exc.page_count += issues.page_count
            exc.continuation_cursor = {"pullRequests": exc.continuation_cursor}
            raise
        try:
            milestones = self._list_paginated(f"/repos/{self._repository_slug}/milestones", {"state": "all"})
        except GitHubPaginationError as exc:
            exc.page_count += issues.page_count + pull_requests.page_count
            exc.continuation_cursor = {"milestones": exc.continuation_cursor}
            raise
        continuation_cursor = {
            key: value
            for key, value in {
                "issues": issues.continuation_cursor,
                "pullRequests": pull_requests.continuation_cursor,
                "milestones": milestones.continuation_cursor,
            }.items()
            if value
        }
        return GitHubSyncPayload(
            # GitHub's Issues endpoint embeds a partial PR representation.  Pull
            # requests are fetched separately below so they have immutable base/
            # head refs and must not be duplicated as issue sources here.
            issues=[item for item in issues.items if not isinstance(item.get("pull_request"), dict)],
            pull_requests=pull_requests.items,
            milestones=milestones.items,
            truncated=issues.truncated or pull_requests.truncated or milestones.truncated,
            page_count=issues.page_count + pull_requests.page_count + milestones.page_count,
            continuation_cursor=continuation_cursor,
        )

    def fetch_issue_timeline(self, issue_number: str) -> list[dict]:
        if not issue_number.isdigit():
            raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub Issue 编号无效")
        return self._list_paginated(f"/repos/{self._repository_slug}/issues/{issue_number}/timeline", {}).items

    def _list_paginated(self, path: str, query: dict[str, str]) -> _PaginatedPayload:
        items: list[dict] = []
        next_path = path
        next_query = {**query, "per_page": "100"}
        expected_suffix = path.removeprefix(f"/repos/{self._repository_slug}")
        for page_count in range(1, _MAX_PAGES + 1):
            try:
                response, link_header = self._get(next_path, next_query)
            except DomainError as exc:
                raise GitHubPaginationError(
                    cause=exc,
                    page_count=page_count - 1,
                    continuation_cursor=self._cursor_from_query(next_query),
                ) from exc
            if not isinstance(response, list):
                raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 来源返回格式无效")
            if not all(isinstance(item, dict) for item in response):
                raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 来源包含无效资源")
            items.extend(response)
            next_url = self._next_url(link_header)
            if next_url is None:
                return _PaginatedPayload(items=items, truncated=False, page_count=page_count, continuation_cursor={})
            next_path, next_query = self._safe_next_page_request(next_url, expected_suffix=expected_suffix)
        return _PaginatedPayload(
            items=items,
            truncated=True,
            page_count=_MAX_PAGES,
            continuation_cursor=self._cursor_from_query(next_query),
        )

    def _get(self, path: str, query: dict[str, str]) -> tuple[object, str | None]:
        target_url = f"{self._api_base_url}{path}?{urlencode(query)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevProof-SourceSync/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        secret = resolve_environment_secret(
            secret_ref=self._secret_ref,
            unavailable_code="SOURCE_SECRET_UNAVAILABLE",
            unavailable_message="服务端未配置 GitHub 来源所需密钥",
        )
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        request = Request(target_url, headers=headers, method="GET")
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self._settings.github_sync_timeout_seconds) as response:
                if response.getcode() < 200 or response.getcode() >= 300:
                    raise DomainError("SOURCE_UNAVAILABLE", f"GitHub 来源返回 HTTP {response.getcode()}")
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self._settings.github_sync_response_limit_bytes:
                    raise DomainError("SOURCE_RESPONSE_TOO_LARGE", "GitHub 来源响应超过允许大小")
                raw = response.read(self._settings.github_sync_response_limit_bytes + 1)
                link_header = response.headers.get("Link")
            if len(raw) > self._settings.github_sync_response_limit_bytes:
                raise DomainError("SOURCE_RESPONSE_TOO_LARGE", "GitHub 来源响应超过允许大小")
            return json.loads(raw.decode("utf-8")), link_header
        except DomainError:
            raise
        except UnicodeDecodeError as exc:
            raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 来源不是 UTF-8 JSON") from exc
        except json.JSONDecodeError as exc:
            raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 来源不是有效 JSON") from exc
        except HTTPError as exc:
            code = "SOURCE_RATE_LIMITED" if exc.code in {403, 429} else "SOURCE_UNAVAILABLE"
            raise DomainError(code, f"GitHub 来源返回 HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise DomainError("SOURCE_UNAVAILABLE", "GitHub 来源当前不可用") from exc

    @staticmethod
    def _next_url(link_header: str | None) -> str | None:
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header, flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _safe_next_page_request(self, next_url: str, *, expected_suffix: str | None = None) -> tuple[str, dict[str, str]]:
        parsed = urlparse(next_url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com":
            raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 分页链接不属于受控 API 主机")
        named_path = f"/repos/{self._repository_slug}{expected_suffix or ''}"
        canonical_pattern = rf"^/repositories/\d+{re.escape(expected_suffix or '')}$"
        if parsed.path != named_path and not re.fullmatch(canonical_pattern, parsed.path):
            raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 分页链接超出当前来源仓库范围")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if not query:
            raise DomainError("SOURCE_RESPONSE_INVALID", "GitHub 分页链接缺少分页参数")
        return parsed.path, query

    @staticmethod
    def _cursor_from_query(query: dict[str, str]) -> dict[str, str]:
        return {key: value for key, value in query.items() if key in {"page", "after", "before", "since"}}
