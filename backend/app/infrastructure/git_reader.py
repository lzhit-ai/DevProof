import base64
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from filelock import FileLock, Timeout

from app.core.config import get_settings
from app.domain.errors import DomainError
from app.domain.ports import FrozenGitDiff, FrozenGitRange, GitReaderPort
from app.infrastructure.credential_resolver import resolve_environment_secret
from app.infrastructure.code_context import enrich_symbol_context
from app.infrastructure.diff_parser import enrich_context, parse_unified_diff


class ReadOnlyGitReader(GitReaderPort):
    """Uses a restricted Git command allowlist in the controlled artifact volume."""

    def freeze_range(self, repository_url: str, base_ref: str, target_ref: str, diff_mode: str, include_paths: list[str], exclude_paths: list[str], credential_ref: str | None = None) -> FrozenGitRange:
        parsed = urlparse(repository_url)
        if parsed.scheme not in {"https", "ssh"} or not parsed.netloc:
            raise DomainError("GIT_RANGE_INVALID", "仓库地址必须是 https 或 ssh 远程地址")
        if diff_mode not in {"TWO_DOT", "THREE_DOT"}:
            raise DomainError("GIT_RANGE_INVALID", "Diff 模式必须是 TWO_DOT 或 THREE_DOT")
        with self._repository_lock(repository_url):
            repository = self._ensure_read_only_clone(repository_url, credential_ref=credential_ref)
            base_sha = self._run(repository, "rev-parse", "--verify", f"{base_ref}^{{commit}}", repository_url=repository_url, credential_ref=credential_ref)
            target_sha = self._run(repository, "rev-parse", "--verify", f"{target_ref}^{{commit}}", repository_url=repository_url, credential_ref=credential_ref)
            merge_base_sha = self._run(repository, "merge-base", base_sha, target_sha, repository_url=repository_url, credential_ref=credential_ref)
            comparison = f"{base_sha}..{target_sha}" if diff_mode == "TWO_DOT" else f"{merge_base_sha}..{target_sha}"
            pathspecs = [*include_paths, *(f":(exclude){path}" for path in exclude_paths)]
            suffix = ("--", *pathspecs) if pathspecs else ()
            diff_bytes = self._run_bytes(repository, "diff", "--no-ext-diff", "--find-renames", "--binary", comparison, *suffix, repository_url=repository_url, credential_ref=credential_ref)
            diff = diff_bytes.decode("utf-8", errors="replace")
            name_status = self._run_bytes(repository, "diff", "--no-ext-diff", "--find-renames", "--name-status", "-z", comparison, *suffix, repository_url=repository_url, credential_ref=credential_ref)
            numstat = self._run_bytes(repository, "diff", "--no-ext-diff", "--find-renames", "--numstat", "-z", comparison, *suffix, repository_url=repository_url, credential_ref=credential_ref)
            coverage = self._coverage(comparison, include_paths, exclude_paths, diff, name_status, numstat)
            settings = get_settings()
            files = parse_unified_diff(diff)
            bundle = enrich_context(
                files,
                read_blob=lambda sha, path: self._run_bytes(repository, "show", f"{sha}:{path}", repository_url=repository_url, credential_ref=credential_ref),
                base_sha=base_sha,
                target_sha=target_sha,
                max_file_bytes=settings.code_review_context_max_file_bytes,
                max_total_bytes=settings.code_review_context_max_total_bytes,
            )
            bundle = enrich_symbol_context(
                bundle,
                target_sha=target_sha,
                read_blob=lambda sha, path: self._run_bytes(repository, "show", f"{sha}:{path}", repository_url=repository_url, credential_ref=credential_ref),
                list_paths=lambda sha: self._list_paths(repository, sha, repository_url=repository_url, credential_ref=credential_ref),
                max_related_symbols=settings.code_review_context_max_related_symbols,
            )
            coverage = {**coverage, "codeReview": bundle["coverage"]}
            return FrozenGitRange(
                base_sha=base_sha,
                target_sha=target_sha,
                merge_base_sha=merge_base_sha,
                diff_hash=f"sha256:{hashlib.sha256(diff_bytes).hexdigest()}",
                coverage=coverage,
                diff=diff_bytes,
                code_change_bundle=bundle,
            )

    def read_frozen_diff(
        self,
        repository_url: str,
        *,
        base_sha: str,
        target_sha: str,
        merge_base_sha: str,
        diff_mode: str,
        include_paths: list[str],
        exclude_paths: list[str],
        expected_diff_hash: str,
        credential_ref: str | None = None,
    ) -> FrozenGitDiff:
        """Re-read the range using frozen SHAs, never the user-selected branch names."""
        with self._repository_lock(repository_url):
            repository = self._ensure_read_only_clone(repository_url, credential_ref=credential_ref)
            self._run(repository, "cat-file", "-e", f"{base_sha}^{{commit}}", repository_url=repository_url, credential_ref=credential_ref)
            self._run(repository, "cat-file", "-e", f"{target_sha}^{{commit}}", repository_url=repository_url, credential_ref=credential_ref)
            comparison = f"{base_sha}..{target_sha}" if diff_mode == "TWO_DOT" else f"{merge_base_sha}..{target_sha}"
            pathspecs = [*include_paths, *(f":(exclude){path}" for path in exclude_paths)]
            suffix = ("--", *pathspecs) if pathspecs else ()
            diff = self._run(repository, "diff", "--no-ext-diff", "--find-renames", "--binary", comparison, *suffix, repository_url=repository_url, credential_ref=credential_ref)
            actual_hash = f"sha256:{hashlib.sha256(diff.encode('utf-8')).hexdigest()}"
            if actual_hash != expected_diff_hash:
                raise DomainError("INPUT_STALE", "冻结 Git 差异校验失败，不能使用已变化的输入继续分析")
            name_status = self._run(repository, "diff", "--no-ext-diff", "--find-renames", "--name-status", comparison, *suffix, repository_url=repository_url, credential_ref=credential_ref)
            numstat = self._run(repository, "diff", "--no-ext-diff", "--find-renames", "--numstat", comparison, *suffix, repository_url=repository_url, credential_ref=credential_ref)
            return FrozenGitDiff(
                diff=diff,
                coverage=self._coverage(comparison, include_paths, exclude_paths, diff, name_status, numstat),
            )

    def read_frozen_blobs(
        self,
        repository_url: str,
        *,
        target_sha: str,
        paths: list[str],
        credential_ref: str | None = None,
    ) -> dict[str, bytes]:
        """Read immutable context only from the local cache; analysis never triggers fetch."""
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", target_sha):
            raise DomainError("GIT_RANGE_INVALID", "冻结提交 SHA 格式无效")
        if not paths or len(paths) > get_settings().code_review_context_max_supplement_requests:
            raise DomainError("GIT_CONTEXT_INVALID", "补充代码上下文的文件数量超出限制")
        normalized = list(dict.fromkeys(paths))
        if any(not path or Path(path).is_absolute() or "\\" in path or ".." in Path(path).parts for path in normalized):
            raise DomainError("GIT_CONTEXT_INVALID", "补充代码上下文包含非法仓库路径")
        with self._repository_lock(repository_url):
            root = Path(get_settings().artifact_root).resolve() / "repositories"
            repository = root / hashlib.sha256(repository_url.encode("utf-8")).hexdigest()
            if not (repository / ".git").exists():
                raise DomainError("GIT_CONTEXT_UNAVAILABLE", "冻结代码缓存已不可用，不能在分析阶段重新拉取仓库")
            # The cache already contains this immutable commit. Do not resolve a remote
            # credential or allow a network path during graph-time supplementation.
            self._run(repository, "cat-file", "-e", f"{target_sha}^{{commit}}", repository_url=repository_url, credential_ref=None)
            return {
                path: self._run_bytes(repository, "show", f"{target_sha}:{path}", repository_url=repository_url, credential_ref=None)
                for path in normalized
            }

    @staticmethod
    def _coverage(comparison: str, include_paths: list[str], exclude_paths: list[str], diff: str, name_status: str | bytes, numstat: str | bytes) -> dict:
        """Make non-text or intentionally skipped Git inputs explicit to the workflow."""
        notices: list[dict] = []
        skipped: list[dict] = []
        name_records: list[tuple[str, list[str]]] = []
        if isinstance(name_status, bytes):
            tokens = [item.decode("utf-8", errors="replace") for item in name_status.split(b"\0") if item]
            index = 0
            while index < len(tokens):
                status = tokens[index]; index += 1
                count = 2 if status.startswith(("R", "C")) else 1
                paths = tokens[index:index + count]; index += count
                if paths:
                    name_records.append((status, paths))
        else:
            for line in name_status.splitlines():
                if not line:
                    continue
                parts = line.split("\t")
                name_records.append((parts[0], parts[1:]))
        changed = ["\t".join([status, *paths]) for status, paths in name_records]
        for status, paths in name_records:
            if status.startswith("R") and len(paths) >= 2:
                notices.append({"kind": "RENAMED", "from": paths[-2], "to": paths[-1]})
            elif status.startswith("D") and paths:
                skipped.append({"kind": "DELETED", "path": paths[-1], "reasonCode": "NO_NEW_SIDE_TEXT"})

        binary_paths = set(re.findall(r"(?m)^Binary files a/(.+?) and b/(.+?) differ$", diff))
        for before, after in binary_paths:
            skipped.append({"kind": "BINARY", "path": after or before, "reasonCode": "BINARY_DIFF"})
        for path in re.findall(r"(?m)^Submodule (.+?) [0-9a-f]+\.\.[0-9a-f]+", diff):
            skipped.append({"kind": "SUBMODULE", "path": path, "reasonCode": "SUBMODULE_POINTER"})

        generated_pattern = re.compile(r"(^|/)(dist|build|coverage|node_modules)/|\.(min\.js|map|lock)$", re.IGNORECASE)
        for _, paths in name_records:
            path = paths[-1]
            if generated_pattern.search(path):
                skipped.append({"kind": "GENERATED", "path": path, "reasonCode": "GENERATED_PATH_RULE"})
        numstat_lines = (numstat.decode("utf-8", errors="replace").split("\0") if isinstance(numstat, bytes) else numstat.splitlines())
        for line in numstat_lines:
            parts = line.split("\t")
            if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
                continue
            if int(parts[0]) + int(parts[1]) > 10_000:
                skipped.append({"kind": "LARGE_FILE", "path": parts[-1], "reasonCode": "DIFF_LINE_THRESHOLD"})
        return {
            "comparison": comparison,
            "changedFiles": changed,
            "includePaths": include_paths,
            "excludePaths": exclude_paths,
            "notices": notices,
            "skipped": skipped,
        }

    def _ensure_read_only_clone(self, repository_url: str, *, credential_ref: str | None) -> Path:
        root = Path(get_settings().artifact_root).resolve() / "repositories"
        root.mkdir(parents=True, exist_ok=True)
        target = root / hashlib.sha256(repository_url.encode("utf-8")).hexdigest()
        if not (target / ".git").exists():
            temporary = Path(tempfile.mkdtemp(prefix=".clone-", dir=root))
            temporary.rmdir()
            try:
                self._run(root, "clone", "--no-checkout", "--filter=blob:none", repository_url, str(temporary), repository_url=repository_url, credential_ref=credential_ref)
                os.replace(temporary, target)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        else:
            self._run(target, "fetch", "--prune", "origin", repository_url=repository_url, credential_ref=credential_ref)
        os.utime(target, None)
        return target

    @staticmethod
    def _list_paths(repository: Path, sha: str, *, repository_url: str, credential_ref: str | None) -> list[str]:
        output = ReadOnlyGitReader._run_bytes(repository, "ls-tree", "-r", "--name-only", "-z", sha, repository_url=repository_url, credential_ref=credential_ref)
        return [item.decode("utf-8", errors="replace") for item in output.split(b"\0") if item]

    @contextmanager
    def _repository_lock(self, repository_url: str):
        root = Path(get_settings().artifact_root).resolve() / "repositories"
        lock_root = root / ".locks"
        lock_root.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(repository_url.encode("utf-8")).hexdigest()
        lock = FileLock(str(lock_root / f"{key}.lock"))
        try:
            with lock.acquire(timeout=get_settings().git_command_timeout_seconds):
                self._prune_cache(root, protected_key=key)
                yield
        except Timeout as exc:
            raise DomainError("GIT_REPOSITORY_BUSY", "同一 Git 仓库正在准备只读快照，请稍后重试") from exc

    @staticmethod
    def _prune_cache(root: Path, *, protected_key: str) -> None:
        """Best-effort TTL cleanup. A repository lock protects active readers."""
        settings = get_settings()
        try:
            usage = shutil.disk_usage(root)
            over_watermark = usage.used * 100 >= usage.total * settings.git_repository_cache_max_usage_percent
        except OSError:
            over_watermark = False
        cutoff = time.time() - settings.git_repository_cache_ttl_hours * 3600
        for candidate in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0):
            if not candidate.is_dir() or candidate.name.startswith(".") or candidate.name == protected_key:
                continue
            try:
                expired = candidate.stat().st_mtime < cutoff
            except OSError:
                continue
            if not expired and not over_watermark:
                continue
            lock = FileLock(str(root / ".locks" / f"{candidate.name}.lock"))
            try:
                with lock.acquire(timeout=0):
                    shutil.rmtree(candidate, ignore_errors=True)
            except Timeout:
                continue

    @staticmethod
    def _run(cwd: Path, *args: str, repository_url: str, credential_ref: str | None) -> str:
        return ReadOnlyGitReader._run_bytes(cwd, *args, repository_url=repository_url, credential_ref=credential_ref).decode("utf-8", errors="replace").strip()

    @staticmethod
    def _run_bytes(cwd: Path, *args: str, repository_url: str, credential_ref: str | None) -> bytes:
        settings = get_settings()
        environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
        parsed_url = urlparse(repository_url)
        if parsed_url.scheme == "ssh":
            environment["GIT_SSH_COMMAND"] = (
                "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "
                f"-o ConnectTimeout={settings.git_ssh_connect_timeout_seconds}"
            )
        if credential_ref:
            parsed = parsed_url
            if parsed.scheme != "https" or (parsed.hostname or "").casefold() != "github.com":
                raise DomainError("GIT_CREDENTIAL_NOT_SUPPORTED", "GitHub Fine-grained PAT 仅支持 HTTPS GitHub 仓库地址")
            token = resolve_environment_secret(
                secret_ref=credential_ref,
                unavailable_code="GIT_CREDENTIAL_UNAVAILABLE",
                unavailable_message="服务端未配置私有 Git 仓库所需密钥",
            )
            authorization = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
            environment.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Basic {authorization}",
                }
            )
        command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "http.followRedirects=false", "-c", "core.quotePath=false", "-C", str(cwd), *args]
        try:
            result = subprocess.run(command, capture_output=True, check=True, text=False, timeout=settings.git_command_timeout_seconds, env=environment, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise DomainError("GIT_RANGE_INVALID", "无法读取只读 Git 范围") from exc
        return result.stdout
