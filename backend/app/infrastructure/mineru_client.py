"""Bounded, read-only MinerU online parsing client for knowledge-source extraction.

MinerU's precision API is asynchronous (submit -> poll) and requires a bearer
token.  Local files are uploaded to an OSS-signed URL, then the batch result is
polled until done; the returned ZIP is unpacked to the Markdown `full.md`,
which the legacy text parser converts into indexable chunks.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from app.core.config import Settings
from app.infrastructure.document_parser import (
    DocumentExtractionError,
    ExtractedDocument,
    MarkdownTextDocumentParser,
)

_API_VERSION = "2022-11-28"  # informative; MinerU does not gate on it
_UPLOAD_BATCH_PATH = "/api/v4/file-urls/batch"
_EXTRACT_RESULTS_PATH = "/api/v4/extract-results/batch"
_ZIP_ENTRY = "full.md"


class MineruParseError(DocumentExtractionError):
    """A bounded MinerU failure with a stable error code and user-facing message."""


def _require_token(settings: Settings) -> str:
    token = (settings.mineru_api_token or "").strip()
    if not token:
        raise MineruParseError(
            "SOURCE_MINERU_TOKEN_UNAVAILABLE", "服务端未配置 MinerU API Token（MINERU_API_TOKEN）"
        )
    return token


def _json_post(url: str, *, payload: dict, token: str, timeout: int) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with build_opener().open(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise MineruParseError("SOURCE_MINERU_UNAVAILABLE", f"MinerU 提交解析任务失败 (HTTP {exc.code})") from exc
    except (URLError, TimeoutError) as exc:
        raise MineruParseError("SOURCE_MINERU_UNAVAILABLE", "MinerU 服务当前不可用") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MineruParseError("SOURCE_MINERU_RESPONSE_INVALID", "MinerU 返回内容不是有效 JSON") from exc


def _upload_bytes(upload_url: str, content: bytes, timeout: int) -> None:
    # MinerU's signed OSS URL is computed without a Content-Type header, so the
    # request must not send one (urllib would otherwise inject a default that
    # breaks the signature and yields HTTP 403 SignatureDoesNotMatch).
    request = Request(upload_url, data=content, method="PUT", headers={"Content-Type": ""})
    try:
        with build_opener().open(request, timeout=timeout) as response:
            response.read()
    except HTTPError as exc:
        raise MineruParseError("SOURCE_MINERU_UPLOAD_FAILED", f"MinerU 文件上传失败 (HTTP {exc.code})") from exc
    except (URLError, TimeoutError) as exc:
        raise MineruParseError("SOURCE_MINERU_UPLOAD_FAILED", "MinerU 文件上传失败，请稍后重试") from exc


def _json_get(url: str, *, token: str, timeout: int) -> dict:
    request = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with build_opener().open(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise MineruParseError("SOURCE_MINERU_UNAVAILABLE", f"MinerU 查询解析结果失败 (HTTP {exc.code})") from exc
    except (URLError, TimeoutError) as exc:
        raise MineruParseError("SOURCE_MINERU_UNAVAILABLE", "MinerU 服务当前不可用") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MineruParseError("SOURCE_MINERU_RESPONSE_INVALID", "MinerU 返回内容不是有效 JSON") from exc


def _fetch_bytes(url: str, *, headers: dict | None, timeout: int, max_bytes: int) -> bytes:
    request = Request(url, headers=headers or {}, method="GET")
    try:
        with build_opener().open(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise MineruParseError("SOURCE_MINERU_RESULT_UNAVAILABLE", "MinerU 解析结果下载失败") from exc
    except (URLError, TimeoutError) as exc:
        raise MineruParseError("SOURCE_MINERU_RESULT_UNAVAILABLE", "MinerU 解析结果下载失败，请稍后重试") from exc
    if len(raw) > max_bytes:
        raise MineruParseError("SOURCE_MINERU_RESULT_TOO_LARGE", "MinerU 解析结果超过允许大小")
    return raw


def _read_markdown_from_zip(zip_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            if _ZIP_ENTRY not in archive.namelist():
                raise MineruParseError("SOURCE_MINERU_RESULT_INVALID", "MinerU 解析结果缺少 Markdown 文件")
            raw = archive.read(_ZIP_ENTRY)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise MineruParseError("SOURCE_MINERU_RESULT_INVALID", "MinerU 解析结果压缩包无效") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MineruParseError("SOURCE_MINERU_RESULT_INVALID", "MinerU 解析结果不是有效 UTF-8") from exc


def parse_document_via_mineru(*, content: bytes, filename: str, settings: Settings, force_ocr: bool | None = None) -> ExtractedDocument:
    """Ingest one file through MinerU's precision API and return chunks."""
    token = _require_token(settings)
    if not content:
        raise MineruParseError("SOURCE_EMPTY", "资料内容不能为空")
    base_url = settings.mineru_api_base_url.rstrip("/")
    timeout = settings.mineru_timeout_seconds
    pool_interval = settings.mineru_poll_interval_seconds
    result_max_bytes = settings.mineru_result_max_bytes
    # The per-file OCR intent is authoritative; when unspecified fall back to the
    # global mineru_force_ocr default.
    is_ocr = settings.mineru_force_ocr if force_ocr is None else force_ocr

    submit_payload = {
        "files": [
            {
                "name": filename,
                "is_ocr": is_ocr,
                "language": settings.mineru_language,
                "enable_table": True,
                "enable_formula": True,
            }
        ],
        "model_version": settings.mineru_model_version,
    }
    submitted = _json_post(
        f"{base_url}{_UPLOAD_BATCH_PATH}",
        payload=submit_payload,
        token=token,
        timeout=timeout,
    )
    if submitted.get("code") != 0:
        raise MineruParseError("SOURCE_MINERU_REJECTED", f"MinerU 拒绝解析任务：{submitted.get('msg') or '未知错误'}")
    batch_id = (submitted.get("data") or {}).get("batch_id")
    upload_urls = (submitted.get("data") or {}).get("file_urls") or []
    if not batch_id or not upload_urls:
        raise MineruParseError("SOURCE_MINERU_RESPONSE_INVALID", "MinerU 未返回上传链接或批次 ID")
    _upload_bytes(upload_urls[0], content, timeout=timeout)

    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() > deadline:
            raise MineruParseError("SOURCE_MINERU_TIMEOUT", "MinerU 解析超时，请稍后重试")
        result = _json_get(
            f"{base_url}{_EXTRACT_RESULTS_PATH}/{batch_id}",
            token=token,
            timeout=timeout,
        )
        if result.get("code") != 0:
            raise MineruParseError("SOURCE_MINERU_REJECTED", f"MinerU 查询失败：{result.get('msg') or '未知错误'}")
        entries = (result.get("data") or {}).get("extract_result") or []
        entry = entries[0] if entries else {}
        state = entry.get("state")
        if state == "done":
            full_zip_url = entry.get("full_zip_url")
            if not full_zip_url:
                raise MineruParseError("SOURCE_MINERU_RESULT_INVALID", "MinerU 未返回解析结果下载地址")
            zip_bytes = _fetch_bytes(full_zip_url, headers=None, timeout=timeout, max_bytes=result_max_bytes)
            markdown = _read_markdown_from_zip(zip_bytes)
            chunks = MarkdownTextDocumentParser().parse(markdown)
            return ExtractedDocument(
                media_type="application/pdf",
                parser_version="mineru-v4",
                chunks=chunks,
                normalized_text=markdown,
                metadata={"extractor": "mineru-v4", "markdownChars": len(markdown)},
            )
        if state == "failed":
            err = entry.get("err_msg") or "MinerU 解析失败"
            raise MineruParseError("SOURCE_MINERU_FAILED", f"MinerU 解析失败：{err}")
        if state in {"waiting-file", "pending", "running", "converting", "uploading"}:
            time.sleep(pool_interval)
            continue
        raise MineruParseError("SOURCE_MINERU_RESPONSE_INVALID", f"MinerU 返回未知处理状态：{state}")
