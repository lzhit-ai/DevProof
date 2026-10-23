"""Regression coverage for strict same-repository delivery evidence matching."""

import unittest

from app.application.services.repository_identity import (
    github_repository_matches,
    github_repository_slug_from_git_url,
)


class RepositoryIdentityTests(unittest.TestCase):
    def test_accepts_https_and_ssh_urls_for_same_github_repository(self) -> None:
        self.assertEqual(
            github_repository_slug_from_git_url("https://github.com/OctoCat/Hello-World.git"),
            "octocat/hello-world",
        )
        self.assertTrue(
            github_repository_matches(
                repository_url="ssh://git@github.com/OctoCat/Hello-World.git",
                repository_slug="octocat/hello-world",
            )
        )

    def test_rejects_a_different_or_non_github_repository(self) -> None:
        self.assertFalse(
            github_repository_matches(
                repository_url="https://github.com/octocat/other-repository.git",
                repository_slug="octocat/hello-world",
            )
        )
        self.assertIsNone(github_repository_slug_from_git_url("https://gitlab.com/octocat/hello-world.git"))
