"""Fixed-command Git capture; never checks out or executes repository code."""

import base64
import os
import re
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from devproof_agent.compute.code_context import enrich_symbol_context
from devproof_agent.compute.diff_parser import enrich_context, parse_unified_diff
from devproof_agent.compute.git_coverage import coverage
from devproof_agent.compute.git_types import GitCaptureRequest, GitCaptureResult, GitRange, GitSettings
from devproof_agent.compute.settings import digest
from devproof_agent.models import AgentError


class GitCapture:
    _gate = threading.Lock()
    def __init__(self, settings: GitSettings, cancelled=lambda: False):
        self.settings = settings
        self.cancelled = cancelled
        self.deadline = time.monotonic() + settings.git_capture_timeout_seconds

    def remaining(self):
        if self.cancelled():
            raise AgentError("COMPUTE_CANCELLED", "调用方已停止 Git 采集")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentError("GIT_CAPTURE_TIMEOUT", "Git 采集超过配置的时间上限")
        return remaining

    @staticmethod
    def remote_url(value: str):
        try:
            url = urlsplit(value)
            if (url.scheme not in {"https", "ssh"} or not url.hostname or url.query or url.fragment
                or not url.path or url.password or (url.scheme == "https" and url.username)
                or any(ord(c) < 32 for c in value)):
                raise ValueError()
            if url.username and not re.fullmatch(r"[A-Za-z0-9_.-]+", url.username):
                raise ValueError()
            _ = url.port
            return url
        except ValueError:
            raise AgentError("GIT_RANGE_INVALID", "仓库地址必须是无内嵌密钥的 HTTPS 或 SSH 远程地址") from None

    def environment(self, request: GitCaptureRequest):
        url = self.remote_url(request.repositoryUrl)
        env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "SSH_AUTH_SOCK") if key in os.environ}
        env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
            GIT_NO_REPLACE_OBJECTS="1", GIT_SSH_COMMAND="ssh -oBatchMode=yes -oStrictHostKeyChecking=yes "
                f"-oConnectTimeout={self.settings.git_ssh_connect_timeout_seconds}")
        if request.credentialRef:
            if request.credentialRef not in {item.strip() for item in self.settings.git_credential_refs.split(",")}:
                raise AgentError("CREDENTIAL_REF_FORBIDDEN", "该 Git 凭据引用未授权给采集服务")
            if url.scheme != "https" or url.hostname.lower() != "github.com":
                raise AgentError("CREDENTIAL_REF_FORBIDDEN", "环境凭据仅支持 GitHub HTTPS 仓库")
            secret = os.environ.get(request.credentialRef, "")
            if not secret.strip():
                raise AgentError("GIT_CREDENTIAL_NOT_CONFIGURED", "仓库凭据引用尚未配置")
            env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                GIT_CONFIG_VALUE_0="Authorization: Basic " + base64.b64encode(("x-access-token:" + secret).encode()).decode("ascii"))
        return env

    def run(self, repository: Path | None, env: dict, limit: int, *args: str) -> bytes:
        command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", "-c", "http.followRedirects=false",
            "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", "-c", "core.quotePath=false"]
        if repository is not None:
            command += ["--git-dir=" + str(repository)]
        stop_at = time.monotonic() + min(self.remaining(), self.settings.git_command_timeout_seconds)
        try:
            process = subprocess.Popen([*command, *args], env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError:
            raise AgentError("GIT_UNAVAILABLE", "Git 程序不可用") from None
        data = bytearray()
        done = threading.Event()
        failure = []

        def consume():
            try:
                while part := process.stdout.read(65536):
                    data.extend(part)
                    if len(data) > limit:
                        failure.append("GIT_OUTPUT_LIMIT")
                        process.kill()
                        break
            except OSError:
                failure.append("GIT_COMMAND_FAILED")
            finally:
                done.set()

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        try:
            while not done.wait(min(0.1, max(0.001, stop_at - time.monotonic()))):
                self.remaining()
                if time.monotonic() >= stop_at:
                    raise AgentError("GIT_COMMAND_TIMEOUT", "Git 命令超过配置的时间上限")
            self.remaining()
            code = process.wait(timeout=max(0.01, stop_at - time.monotonic()))
            if failure:
                raise AgentError(failure[0], "Git 输出超过上限或读取失败")
            if code:
                raise AgentError("GIT_COMMAND_FAILED", "Git 读取失败，请检查远程权限、引用和仓库状态")
            return bytes(data)
        except subprocess.TimeoutExpired:
            raise AgentError("GIT_COMMAND_TIMEOUT", "Git 命令超过配置的时间上限") from None
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=2)
            process.stdout.close()

    @contextmanager
    def repository_lock(self, directory: Path):
        # POSIX record locks interoperate with Java FileChannel (flock does not).
        # Record locks are process-wide, so serialize Python capture threads too.
        if not self._gate.acquire(blocking=False):
            raise AgentError("REPOSITORY_BUSY", "Git 采集执行槽已占用，请稍后重试")
        try:
            with open(directory / "capture.lock", "a+b") as lock:
                try:
                    if os.name == "nt":
                        import msvcrt
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise AgentError("REPOSITORY_BUSY", "仓库正在抓取，请稍后重试") from None
                yield
        finally:
            self._gate.release()

    def capture(self, request: GitCaptureRequest, request_hash: str) -> GitCaptureResult:
        if request.configurationHash != self.settings.configuration_hash():
            raise AgentError("COMPUTE_CONFIG_CHANGED", "Git 计算配置与请求冻结版本不一致")
        env = self.environment(request)
        root = Path(self.settings.repository_cache_root).resolve()
        directory = root / str(request.projectId) / str(request.repositoryId)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            directory = directory.resolve()
            if not directory.is_relative_to(root):
                raise OSError("Repository cache scope")
            with self.repository_lock(directory):
                bare = directory / "repository.git"
                if bare.exists() and not bare.resolve().is_relative_to(directory):
                    raise OSError("Repository cache scope")
                if not (bare / "HEAD").exists():
                    self.run(None, env, 65536, "init", "--bare", str(bare))
                refs = (request.baseRef, request.targetRef)
                if all(re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", ref) for ref in refs):
                    # PR inputs already pin both commits. Fetch only missing commits and
                    # retain them locally, without refreshing unrelated branches/tags.
                    missing = []
                    for ref in dict.fromkeys(refs):
                        try:
                            cached = self.run(bare, env, 256, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode("ascii").strip()
                            # Negotiation advertises refs, not unreferenced objects left
                            # by an interrupted fetch. Keep cached commits reachable.
                            self.run(bare, env, 256, "update-ref", "refs/devproof/commits/" + ref, cached)
                        except AgentError as exc:
                            if exc.code != "GIT_COMMAND_FAILED":
                                raise
                            missing.append(ref)
                    if missing:
                        self.run(bare, env, 65536, "fetch", "--no-tags", "--", request.repositoryUrl,
                            *(ref + ":refs/devproof/commits/" + ref for ref in missing))
                    head = request.baseRef
                else:
                    # Named refs must still be refreshed before resolving revisions.
                    self.run(bare, env, 65536, "fetch", "--prune", "--", request.repositoryUrl,
                        "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*")
                    self.run(bare, env, 65536, "fetch", "--no-tags", "--", request.repositoryUrl, "HEAD")
                    head = self.run(bare, env, 256, "rev-parse", "--verify", "FETCH_HEAD^{commit}").decode("ascii").strip()
                shas = []
                for ref in (request.baseRef, request.targetRef):
                    shas.append(self.resolve(bare, env, request.repositoryUrl, ref, head))
                return self.frozen(bare, env, request, request_hash, *shas)
        except OSError:
            raise AgentError("REPOSITORY_STORAGE_UNAVAILABLE", "仓库缓存不可读写") from None

    def resolve(self, bare: Path, env: dict, url: str, ref: str, head: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", head):
            raise AgentError("GIT_SHA_INVALID", "Git 未返回完整默认提交 SHA")
        revision = re.sub(r"^HEAD(?=$|[~^])", head, ref)
        if revision.startswith("refs/heads/"):
            revision = "refs/remotes/origin/" + revision.removeprefix("refs/heads/")
        candidates = ["refs/remotes/origin/" + revision, revision]
        for candidate in candidates:
            try:
                sha = self.run(bare, env, 256, "rev-parse", "--verify", "--end-of-options", candidate + "^{commit}").decode("ascii").strip()
                if re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", sha):
                    return sha
            except AgentError as exc:
                if exc.code != "GIT_COMMAND_FAILED":
                    raise
        # Explicit PR refs and reachable SHAs need not be under the advertised heads.
        self.run(bare, env, 65536, "fetch", "--no-tags", "--", url, ref)
        sha = self.run(bare, env, 256, "rev-parse", "--verify", "FETCH_HEAD^{commit}").decode("ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", sha):
            raise AgentError("GIT_SHA_INVALID", "Git 未返回完整提交 SHA")
        return sha

    def frozen(self, bare: Path, env: dict, request: GitRange, request_hash: str,
               base: str, target: str) -> GitCaptureResult:
        """Read only existing commit objects; also used for inspecting actual local history."""
        import json
        merge = self.run(bare, env, 256, "merge-base", base, target).decode("ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", merge):
            raise AgentError("GIT_SHA_INVALID", "Git 未返回完整合并基线 SHA")
        effective = base if request.diffMode == "TWO_DOT" else merge
        comparison = effective + ".." + target
        suffix = ("--", *request.includePaths, *(":(exclude)" + path for path in request.excludePaths))
        raw = self.run(bare, env, self.settings.git_diff_max_bytes, "diff", "--no-ext-diff", "--no-textconv", "--find-renames", "--binary", comparison, *suffix)
        if not raw:
            raise AgentError("GIT_DIFF_EMPTY", "指定范围没有可冻结的 Git Diff")
        names = self.run(bare, env, self.settings.git_tree_max_bytes, "diff", "--no-ext-diff", "--no-textconv", "--find-renames", "--name-status", "-z", comparison, *suffix)
        stats = self.run(bare, env, self.settings.git_tree_max_bytes, "diff", "--no-ext-diff", "--no-textconv", "--find-renames", "--numstat", "-z", comparison, *suffix)
        text = raw.decode("utf-8", errors="replace")
        remaining = self.settings.code_review_context_max_total_bytes
        cached = {}

        def blob(sha, path):
            nonlocal remaining
            key = sha, path
            if key not in cached:
                if remaining <= 0:
                    raise AgentError("GIT_CONTEXT_LIMIT", "代码上下文已达到配置上限")
                value = self.run(bare, env, min(remaining, self.settings.code_review_context_max_file_bytes), "cat-file", "blob", sha + ":" + path)
                cached[key] = value
                remaining -= len(value)
            return cached[key]

        bundle = enrich_context(parse_unified_diff(text), read_blob=blob, base_sha=effective, target_sha=target,
            max_file_bytes=self.settings.code_review_context_max_file_bytes,
            max_total_bytes=self.settings.code_review_context_max_total_bytes)
        bundle = enrich_symbol_context(bundle, target_sha=target, read_blob=blob,
            list_paths=lambda sha: [path.decode("utf-8", errors="replace") for path in self.run(bare, env,
                self.settings.git_tree_max_bytes, "ls-tree", "-rz", "--name-only", "--full-tree", sha).split(b"\0") if path],
            max_related_symbols=self.settings.code_review_context_max_related_symbols)
        self.remaining()
        bundle_raw = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return GitCaptureResult(requestHash=request_hash, configurationHash=request.configurationHash,
            baseSha=base, targetSha=target, mergeBaseSha=merge, effectiveBaseSha=effective,
            diffHash=digest(raw), diffBase64=base64.b64encode(raw).decode("ascii"),
            bundleJson=bundle_raw, bundleHash=digest(bundle_raw.encode("utf-8")),
            coverage={**coverage(comparison, request.includePaths, request.excludePaths, text, names, stats), "codeReview": bundle["coverage"]})
