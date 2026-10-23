from app.infrastructure.diff_parser import enrich_context, parse_unified_diff
from app.infrastructure.git_reader import ReadOnlyGitReader
from app.core.config import get_settings
from app.domain.errors import DomainError
from app.application.services.code_review_service import plan_code_review, plan_code_review_challenges
from app.domain.model_contracts import CodeReviewFindingChallengeProposal
from types import SimpleNamespace
import subprocess
import hashlib
import shutil
from uuid import uuid4
import pytest


def test_canonical_diff_preserves_added_deleted_and_renamed_hunks() -> None:
    diff = """diff --git a/旧路径.txt b/旧路径.txt
index 1111111..2222222 100644
--- a/旧路径.txt
+++ b/旧路径.txt
@@ -1,2 +1,2 @@
-before
+after
 keep
diff --git a/remove.py b/remove.py
deleted file mode 100644
index 1111111..0000000
--- a/remove.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
"""
    files = parse_unified_diff(diff)
    assert [(item.path, item.edit_type) for item in files] == [("旧路径.txt", "MODIFIED"), ("remove.py", "DELETED"), ("new.py", "RENAMED")]
    assert files[0].hunks and files[0].hunks[0].old_start == 1 and files[0].hunks[0].new_end == 2
    assert "-gone" in files[1].hunks[0].payload


def test_context_is_bounded_and_never_changes_hunk_payload() -> None:
    diff = """diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-one
+two
"""
    files = parse_unified_diff(diff)
    bundle = enrich_context(
        files,
        read_blob=lambda sha, path: b"one\n" if sha == "base" else b"two\n",
        base_sha="base",
        target_sha="target",
        max_file_bytes=32,
        max_total_bytes=32,
    )
    item = bundle["files"][0]
    assert item["context_state"] == "COMPLETE"
    assert item["base_context"] == "one\n"
    assert item["hunks"][0]["payload"] == "-one\n+two"


def test_context_uses_patch_only_for_binary_blob() -> None:
    diff = """diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-one
+two
"""
    files = parse_unified_diff(diff)
    bundle = enrich_context(
        files,
        read_blob=lambda sha, path: b"\0binary",
        base_sha="base",
        target_sha="target",
        max_file_bytes=32,
        max_total_bytes=32,
    )
    assert bundle["files"][0]["context_state"] == "PATCH_ONLY"
    assert bundle["files"][0]["context_reason_code"] == "BINARY_BLOB"


def test_coverage_uses_nul_delimited_paths() -> None:
    coverage = ReadOnlyGitReader._coverage(
        "base..target",
        [],
        [],
        "",
        "R100\0旧 名.py\0新 名.py\0M\0中文 路径.py\0".encode(),
        "1\t0\t中文 路径.py\0".encode(),
    )
    assert coverage["changedFiles"] == ["R100\t旧 名.py\t新 名.py", "M\t中文 路径.py"]
    assert coverage["notices"] == [{"kind": "RENAMED", "from": "旧 名.py", "to": "新 名.py"}]


def test_code_review_budget_keeps_hunk_before_context() -> None:
    changes, coverage = plan_code_review(
        bundle={"files": [{"path": "a.py", "binary": False, "context_state": "COMPLETE", "base_context": "x" * 100, "target_context": "y" * 100, "hunks": [{"header": "@@ -1 +1 @@", "old_start": 1, "old_end": 1, "new_start": 1, "new_end": 1, "payload": "+x"}]}]},
        evidence_by_locator={("a.py", "@@ -1 +1 @@"): "evidence-1"},
        claims=[SimpleNamespace(id="claim-1", text="验收项")],
        char_budget=300,
    )
    assert changes and changes[0]["hunks"]
    assert changes[0]["contextOnly"] == {"base": None, "target": None}
    assert any(item["reasonCode"] == "CODE_CONTEXT_BUDGET_EXHAUSTED" for item in coverage["details"]["unanalysed"])


def test_reader_freezes_actual_local_git_range_without_checkout(tmp_path) -> None:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True).stdout.strip()

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (tmp_path / "中文 文件.py").write_text("value = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "中文 文件.py").write_text("value = 2\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "target")
    target = git("rev-parse", "HEAD")

    class LocalReader(ReadOnlyGitReader):
        def _ensure_read_only_clone(self, repository_url: str, *, credential_ref: str | None):
            return tmp_path

    frozen = LocalReader().freeze_range("https://github.com/example/repo.git", base, target, "TWO_DOT", [], [])
    assert frozen.base_sha == base
    assert frozen.target_sha == target
    assert frozen.diff.startswith(b"diff --git")
    assert frozen.code_change_bundle["files"][0]["path"] == "中文 文件.py"
    assert frozen.code_change_bundle["files"][0]["context_state"] == "COMPLETE"


def test_reader_freeze_collects_sha_bound_java_import_context(tmp_path) -> None:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True).stdout.strip()

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (tmp_path / "src" / "com" / "example" / "config").mkdir(parents=True)
    (tmp_path / "src" / "PaymentService.java").write_text(
        "import com.example.config.RetryPolicy;\nclass PaymentService { void pay() { } }\n", encoding="utf-8"
    )
    (tmp_path / "src" / "com" / "example" / "config" / "RetryPolicy.java").write_text(
        "package com.example.config; public class RetryPolicy { public static void run() {} }\n", encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "src" / "PaymentService.java").write_text(
        "import com.example.config.RetryPolicy;\nclass PaymentService { void pay() { RetryPolicy.run(); } }\n", encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-m", "target")
    target = git("rev-parse", "HEAD")

    class LocalReader(ReadOnlyGitReader):
        def _ensure_read_only_clone(self, repository_url: str, *, credential_ref: str | None):
            return tmp_path

    frozen = LocalReader().freeze_range("https://github.com/example/repo.git", base, target, "TWO_DOT", [], [])
    assert frozen.code_change_bundle["schemaVersion"] == "code-change-bundle-v2"
    assert any(item["symbol"] == "RetryPolicy" and item["relation"] == "DIRECT_IMPORT" for item in frozen.code_change_bundle["contexts"])
    assert all(item["commitSha"] == target for item in frozen.code_change_bundle["contexts"])


def test_frozen_blob_read_uses_cached_sha_without_fetch(tmp_path, monkeypatch) -> None:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True).stdout.strip()

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "RetryPolicy.py").write_text("class RetryPolicy:\n    pass\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "target")
    target = git("rev-parse", "HEAD")
    repository_url = "https://github.com/example/frozen-context.git"
    artifact_root = tmp_path.parent / "artifacts"
    cached = artifact_root / "repositories" / hashlib.sha256(repository_url.encode("utf-8")).hexdigest()
    cached.parent.mkdir(parents=True)
    shutil.copytree(tmp_path, cached)
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifact_root))
    get_settings.cache_clear()
    try:
        class CachedOnlyReader(ReadOnlyGitReader):
            def _ensure_read_only_clone(self, *args, **kwargs):  # pragma: no cover - must never be called
                raise AssertionError("supplemental context must not fetch")

        reader = CachedOnlyReader()
        blobs = reader.read_frozen_blobs(repository_url, target_sha=target, paths=["src/RetryPolicy.py"])
        assert b"RetryPolicy" in blobs["src/RetryPolicy.py"]
        with pytest.raises(DomainError) as raised:
            reader.read_frozen_blobs(repository_url, target_sha=target, paths=["../outside.py"])
        assert raised.value.code == "GIT_CONTEXT_INVALID"
    finally:
        get_settings.cache_clear()


def test_finding_challenge_budget_keeps_original_hunk_and_claim() -> None:
    finding_id, evidence_id, claim_id = uuid4(), uuid4(), uuid4()
    findings, changes, claims, coverage = plan_code_review_challenges(
        bundle={"files": [{"path": "a.py", "old_path": None, "edit_type": "MODIFIED", "base_context": "old", "target_context": "new", "hunks": [{"header": "@@ -1 +1 @@", "old_start": 1, "old_end": 1, "new_start": 1, "new_end": 1, "payload": "-old\n+new"}]}]},
        findings=[SimpleNamespace(id=finding_id, evidence_id=evidence_id, claim_id=claim_id, finding_kind="BUG", severity="HIGH", title="问题", problem="问题描述", trigger_scenario="触发场景", recommendation="修复建议", confidence=0.8)],
        evidence_by_id={evidence_id: SimpleNamespace(id=evidence_id, locator={"path": "a.py", "hunk": "@@ -1 +1 @@"})},
        claims_by_id={claim_id: SimpleNamespace(id=claim_id, text="验收项")},
        char_budget=4_000,
        max_findings=10,
    )
    assert findings[0]["findingId"] == str(finding_id)
    assert changes[0]["hunks"][0]["evidenceId"] == str(evidence_id)
    assert claims == [{"id": str(claim_id), "text": "验收项"}]
    assert coverage["details"]["selectedFindingIds"] == [str(finding_id)]


def test_finding_challenge_schema_requires_hunk_evidence() -> None:
    with pytest.raises(ValueError):
        CodeReviewFindingChallengeProposal(finding_id=uuid4(), verdict="SUPPORTED", reason="无证据", evidence_ids=[])
