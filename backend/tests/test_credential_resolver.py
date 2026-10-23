"""Credential-reference tests: values remain runtime-only and never enter Git command arguments."""

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.domain.errors import DomainError
from app.infrastructure.credential_resolver import normalize_secret_ref, resolve_environment_secret
from app.infrastructure.git_reader import ReadOnlyGitReader


class CredentialResolverTests(unittest.TestCase):
    def test_validates_and_resolves_an_environment_reference(self) -> None:
        self.assertEqual(normalize_secret_ref(" GITHUB_SOURCE_TOKEN "), "GITHUB_SOURCE_TOKEN")
        with self.assertRaisesRegex(DomainError, "环境变量名称"):
            normalize_secret_ref("github-token")

        os.environ["TEST_GITHUB_READ_TOKEN"] = "test-private-token-value"
        try:
            value = resolve_environment_secret(
                secret_ref="TEST_GITHUB_READ_TOKEN",
                unavailable_code="SOURCE_SECRET_UNAVAILABLE",
                unavailable_message="missing",
            )
        finally:
            del os.environ["TEST_GITHUB_READ_TOKEN"]
        self.assertEqual(value, "test-private-token-value")

    def test_git_uses_a_process_header_not_token_url_or_arguments(self) -> None:
        token = "test-private-token-value"
        os.environ["TEST_GITHUB_READ_TOKEN"] = token
        completed = SimpleNamespace(stdout=b"")
        try:
            with patch("app.infrastructure.git_reader.subprocess.run", return_value=completed) as run:
                ReadOnlyGitReader._run(
                    Path("."),
                    "fetch",
                    "--prune",
                    "origin",
                    repository_url="https://github.com/octocat/private-repository.git",
                    credential_ref="TEST_GITHUB_READ_TOKEN",
                )
        finally:
            del os.environ["TEST_GITHUB_READ_TOKEN"]

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertNotIn(token, " ".join(command))
        self.assertNotIn(token, "https://github.com/octocat/private-repository.git")
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "http.extraHeader")
        self.assertNotIn(token, environment["GIT_CONFIG_VALUE_0"])
        self.assertIn("http.followRedirects=false", command)

    def test_missing_reference_reports_a_stable_code_without_secret_content(self) -> None:
        with self.assertRaises(DomainError) as raised:
            resolve_environment_secret(
                secret_ref="MISSING_GITHUB_READ_TOKEN",
                unavailable_code="GIT_CREDENTIAL_UNAVAILABLE",
                unavailable_message="服务端未配置私有 Git 仓库所需密钥",
            )

        self.assertEqual(raised.exception.code, "GIT_CREDENTIAL_UNAVAILABLE")
        self.assertNotIn("MISSING_GITHUB_READ_TOKEN", raised.exception.message)
