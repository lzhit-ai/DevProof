"""Regression coverage for cursor-compatible GitHub Link pagination."""

import unittest

from app.domain.errors import DomainError
from app.infrastructure.github_source_client import GitHubPaginationError, GitHubSourceClient, _PaginatedPayload


class GitHubSourcePaginationTests(unittest.TestCase):
    def test_sync_fetches_full_pull_requests_and_keeps_issue_discussions_out_of_delivery_input(self) -> None:
        client = object.__new__(GitHubSourceClient)
        client._repository_slug = "octocat/example"

        def fake_list(path: str, _query: dict[str, str]):
            if path.endswith("/issues"):
                return _PaginatedPayload(
                    items=[{"number": 11, "title": "咨询"}, {"number": 12, "pull_request": {"url": "partial"}}],
                    truncated=False,
                    page_count=1,
                    continuation_cursor={},
                )
            if path.endswith("/pulls"):
                return _PaginatedPayload(
                    items=[{"number": 12, "base": {"ref": "main", "sha": "base"}, "head": {"ref": "feature", "sha": "head"}}],
                    truncated=False,
                    page_count=1,
                    continuation_cursor={},
                )
            return _PaginatedPayload(items=[], truncated=False, page_count=1, continuation_cursor={})

        client._list_paginated = fake_list
        result = client.fetch()

        self.assertEqual([item["number"] for item in result.issues], [11])
        self.assertEqual([item["number"] for item in result.pull_requests], [12])
        self.assertEqual(result.page_count, 3)

    def test_follows_the_next_link_instead_of_constructing_page_numbers(self) -> None:
        client = object.__new__(GitHubSourceClient)
        client._repository_slug = "octocat/example"
        calls: list[tuple[str, dict[str, str]]] = []
        responses = iter(
            [
                (
                    [{"number": 1}],
                    '<https://api.github.com/repositories/1296269/issues?after=opaque-cursor&per_page=100>; rel="next"',
                ),
                ([{"number": 2}], None),
            ]
        )

        def fake_get(path: str, query: dict[str, str]):
            calls.append((path, query))
            return next(responses)

        client._get = fake_get
        result = client._list_paginated("/repos/octocat/example/issues", {"state": "all"})

        self.assertEqual([item["number"] for item in result.items], [1, 2])
        self.assertFalse(result.truncated)
        self.assertEqual(result.page_count, 2)
        self.assertEqual(calls[1][1]["after"], "opaque-cursor")
        self.assertNotIn("page", calls[1][1])

    def test_rejects_a_next_link_outside_the_bound_repository(self) -> None:
        client = object.__new__(GitHubSourceClient)
        client._repository_slug = "octocat/example"

        with self.assertRaisesRegex(DomainError, "超出当前来源仓库范围"):
            client._safe_next_page_request("https://api.github.com/repos/other/repository/issues?after=opaque")

    def test_records_safe_cursor_when_a_later_page_fails(self) -> None:
        client = object.__new__(GitHubSourceClient)
        client._repository_slug = "octocat/example"
        responses = iter(
            [
                (
                    [{"number": 1}],
                    '<https://api.github.com/repos/octocat/example/issues?after=opaque-cursor&per_page=100>; rel="next"',
                ),
                DomainError("SOURCE_UNAVAILABLE", "GitHub 来源当前不可用"),
            ]
        )

        def fake_get(path: str, query: dict[str, str]):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        client._get = fake_get
        with self.assertRaises(GitHubPaginationError) as raised:
            client._list_paginated("/repos/octocat/example/issues", {"state": "all"})

        self.assertEqual(raised.exception.code, "SOURCE_UNAVAILABLE")
        self.assertEqual(raised.exception.page_count, 1)
        self.assertEqual(raised.exception.continuation_cursor, {"after": "opaque-cursor"})
