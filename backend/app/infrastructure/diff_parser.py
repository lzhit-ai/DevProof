"""Canonical, non-executing representation of a frozen Git diff."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Callable


_HUNK = re.compile(r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<label>.*)$")
_DIFF = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass
class CanonicalHunk:
    header: str
    old_start: int | None
    old_end: int | None
    new_start: int | None
    new_end: int | None
    payload: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CanonicalDiffFile:
    path: str
    old_path: str | None
    edit_type: str
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    patch: str = ""
    hunks: list[CanonicalHunk] | None = None
    base_context: str | None = None
    target_context: str | None = None
    context_state: str = "PATCH_ONLY"
    context_reason_code: str | None = None

    def as_dict(self) -> dict:
        value = asdict(self)
        value["hunks"] = [item.as_dict() for item in self.hunks or []]
        return value


def _range_end(start: int | None, count: int | None) -> int | None:
    if start is None:
        return None
    return start + max((count or 1) - 1, 0)


def _edit_type(old_path: str | None, path: str | None, patch: list[str]) -> str:
    content = "\n".join(patch)
    if "GIT binary patch" in content or "Binary files " in content:
        return "BINARY"
    if "Subproject commit " in content:
        return "SUBMODULE"
    if any(line.startswith("new file mode ") for line in patch):
        return "ADDED"
    if any(line.startswith("deleted file mode ") for line in patch):
        return "DELETED"
    if any(line.startswith("rename from ") for line in patch):
        return "RENAMED"
    if any(line.startswith("copy from ") for line in patch):
        return "COPIED"
    if any(line.startswith("old mode ") or line.startswith("new mode ") for line in patch):
        return "TYPE_CHANGED"
    return "MODIFIED" if old_path and path else "UNKNOWN"


def parse_unified_diff(diff: str) -> list[CanonicalDiffFile]:
    """Parse only frozen patch text; no file-system or Git access occurs here."""
    files: list[CanonicalDiffFile] = []
    current_lines: list[str] = []
    current_old: str | None = None
    current_path: str | None = None

    def flush() -> None:
        nonlocal current_lines, current_old, current_path
        if current_path is None and current_old is None:
            current_lines = []
            return
        path = current_path or current_old or "unknown"
        old_path = current_old
        for line in current_lines:
            if line.startswith("rename from ") or line.startswith("copy from "):
                old_path = line.split(" ", 2)[-1]
            elif line.startswith("rename to ") or line.startswith("copy to "):
                path = line.split(" ", 2)[-1]
            elif line.startswith("--- ") and line != "--- /dev/null":
                old_path = line[4:].removeprefix("a/").rstrip("\t")
            elif line.startswith("+++ ") and line != "+++ /dev/null":
                path = line[4:].removeprefix("b/").rstrip("\t")
        hunks: list[CanonicalHunk] = []
        hunk_lines: list[str] = []
        hunk_match: re.Match[str] | None = None

        def flush_hunk() -> None:
            nonlocal hunk_lines, hunk_match
            if hunk_match is None:
                return
            old_start = int(hunk_match.group("old_start"))
            new_start = int(hunk_match.group("new_start"))
            old_count = int(hunk_match.group("old_count") or "1")
            new_count = int(hunk_match.group("new_count") or "1")
            hunks.append(CanonicalHunk(
                header=hunk_match.group(0),
                old_start=old_start,
                old_end=_range_end(old_start, old_count),
                new_start=new_start,
                new_end=_range_end(new_start, new_count),
                payload="\n".join(hunk_lines),
            ))
            hunk_lines = []
            hunk_match = None

        additions = deletions = 0
        for line in current_lines:
            match = _HUNK.match(line)
            if match:
                flush_hunk()
                hunk_match = match
                continue
            if hunk_match is not None:
                hunk_lines.append(line)
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
        flush_hunk()
        edit_type = _edit_type(old_path, path, current_lines)
        files.append(CanonicalDiffFile(
            path=path,
            old_path=old_path,
            edit_type=edit_type,
            additions=additions,
            deletions=deletions,
            binary=edit_type in {"BINARY", "SUBMODULE"},
            patch="\n".join(current_lines),
            hunks=hunks,
        ))
        current_lines = []
        current_old = None
        current_path = None

    for line in diff.splitlines():
        match = _DIFF.match(line)
        if match:
            flush()
            current_old = match.group(1).rstrip("\t")
            current_path = match.group(2).rstrip("\t")
        if current_path is not None or current_old is not None:
            current_lines.append(line)
    flush()
    return files


def enrich_context(
    files: list[CanonicalDiffFile],
    *,
    read_blob: Callable[[str, str], bytes],
    base_sha: str,
    target_sha: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> dict:
    """Attach bounded, text-only base/target context without changing evidence payloads."""
    remaining = max_total_bytes
    for item in files:
        if item.binary or item.edit_type in {"SUBMODULE", "UNKNOWN"}:
            item.context_state, item.context_reason_code = "SKIPPED", "NON_TEXT_CHANGE"
            continue
        try:
            base = b"" if item.edit_type == "ADDED" else read_blob(base_sha, item.old_path or item.path)
            target = b"" if item.edit_type == "DELETED" else read_blob(target_sha, item.path)
            total = len(base) + len(target)
            if b"\0" in base or b"\0" in target:
                item.context_state, item.context_reason_code = "PATCH_ONLY", "BINARY_BLOB"
            elif total > max_file_bytes:
                item.context_state, item.context_reason_code = "PATCH_ONLY", "FILE_CONTEXT_LIMIT"
            elif total > remaining:
                item.context_state, item.context_reason_code = "PATCH_ONLY", "TOTAL_CONTEXT_LIMIT"
            else:
                item.base_context = base.decode("utf-8", errors="replace")
                item.target_context = target.decode("utf-8", errors="replace")
                item.context_state, item.context_reason_code = "COMPLETE", None
                remaining -= total
        except Exception:
            item.context_state, item.context_reason_code = "PATCH_ONLY", "GIT_CONTEXT_UNAVAILABLE"
    return {
        "schemaVersion": "code-change-bundle-v1",
        "files": [item.as_dict() for item in files],
        "coverage": {
            "fileCount": len(files),
            "hunkCount": sum(len(item.hunks or []) for item in files),
            "contextCompleteFiles": sum(item.context_state == "COMPLETE" for item in files),
            "patchOnlyFiles": sum(item.context_state == "PATCH_ONLY" for item in files),
            "skippedFiles": sum(item.context_state == "SKIPPED" for item in files),
            "contextBudgetBytes": max_total_bytes,
            "contextRemainingBytes": remaining,
        },
    }
