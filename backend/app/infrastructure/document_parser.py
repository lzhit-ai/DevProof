"""Controlled multi-format document extraction with evidence locators.

Binary formats (PDF, Office, images) are delegated to the online MinerU
precision API; plain and structured text are parsed locally.  No extractor
executes document macros, scripts, embedded objects, archive members or remote
URLs.
"""

from __future__ import annotations

import json
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
import yaml

from app.core.config import get_settings
from app.domain.ports import DocumentParserPort, ParsedDocumentChunk


class DocumentExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractedDocument:
    media_type: str
    parser_version: str
    chunks: list[ParsedDocumentChunk]
    normalized_text: str
    metadata: dict


class MarkdownTextDocumentParser(DocumentParserPort):
    """结构感知的 Markdown 分块器,用于纯文本与规范化抽取文本。

    分块依据 Markdown 结构而非仅看空行:标题携带其下内容(标题+正文一体),
    而连续列表、整张表格、整个代码围栏作为原子单元整体保留。块大小向
    ``target_chars`` 收敛:过大的单元在句末/列表项边界切分,过短块与相邻块
    合并,避免微小标题或逐条碎片存活。``locator`` 偏移基于字节累计位置计算,
    ``charStart``/``charEnd`` 精确对齐原文。
    """

    version = "knowledge-extraction-v1"

    target_chars = 600
    min_chars = 120
    max_list_items = 8

    def parse(self, content: str) -> list[ParsedDocumentChunk]:
        normalized = content.replace("\r\n", "\n")
        lines = normalized.split("\n")
        offsets = self._line_offsets(lines)
        units = self._collect_units(lines)
        merged = self._merge_units(units)
        return self._finalize(lines, offsets, merged)

    # ---- 结构扫描 --------------------------------------------------------

    def _line_kind(self, line: str) -> str:
        # 顺序有讲究:标题不是列表;代码围栏需先于表格识别。
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            return "fence"
        if stripped.startswith("|") or self._is_table_separator(stripped):
            return "table"
        # 标题(如 #、##)
        if self._heading_level(stripped):
            return "heading"
        if self._is_list_item(stripped):
            return "list"
        if stripped.startswith(">"):
            return "quote"
        if not stripped:
            return "blank"
        return "text"

    @staticmethod
    def _heading_level(stripped: str) -> int:
        if not stripped or stripped[0] != "#":
            return 0
        level = 0
        for ch in stripped:
            if ch == "#":
                level += 1
            else:
                break
        # 标题后必须跟空白,否则是孤立的 '#'。
        if level and len(stripped) > level and stripped[level] != " ":
            return 0
        return level

    @staticmethod
    def _is_list_item(stripped: str) -> bool:
        # 无序列表 - * +;有序列表 1.  1)  1、
        return bool(
            re.match(r"^[-*+]\s+", stripped)
            or re.match(r"^\d{1,3}[.)、]\s*\S", stripped)
            or re.match(r"^[一二三四五六七八九十]+[、.，]\s*\S", stripped)
        )

    @staticmethod
    def _is_table_separator(stripped: str) -> bool:
        return "|" in stripped and "-" in stripped and ("---" in stripped or ":" in stripped)

    # ---- 单元收集(逻辑块,结构上原子) -------------------------------------

    def _collect_units(self, lines: list[str]) -> list[dict]:
        """把行转成逻辑单元;每个单元是「标题+正文」就绪的形式。"""
        units: list[dict] = []
        i = 0
        n = len(lines)
        # 每个单元携带:起始行号 start、结束行号(不含)end、
        # 标题层级 level(0=正文)、是否必须保持原子 atomic。
        while i < n:
            stripped = lines[i].lstrip()
            kind = self._line_kind(lines[i])
            if kind == "blank":
                i += 1
                continue
            start = i
            if kind == "fence":
                i = self._consume_fence(lines, i)
                units.append(self._unit(lines, start, i, level=0, atomic=True))
                continue
            if kind == "table":
                i = self._consume_table(lines, i)
                units.append(self._unit(lines, start, i, level=0, atomic=True))
                continue
            if kind == "heading":
                level = self._heading_level(stripped)
                i = start + 1
                # 吞并标题下方的正文,直到下一个标题(任意层级)为止,
                # 使「标题+正文」同属一个逻辑单元。
                while i < n:
                    s = lines[i].lstrip()
                    if not s:
                        i += 1
                        continue
                    # 任一新标题都开启新的块(标题+正文一体)
                    if self._line_kind(lines[i]) == "heading":
                        break
                    i += 1
                units.append(self._unit(lines, start, i, level=level, atomic=False))
                continue
            if kind == "list":
                # 连续列表组作为一个原子单元(不逐条拆分)
                i = self._consume_list(lines, i)
                units.append(self._unit(lines, start, i, level=0, atomic=True))
                continue
            if kind == "quote":
                i = self._consume_continuous(lines, i, lambda ln: self._line_kind(ln) == "quote")
                units.append(self._unit(lines, start, i, level=0, atomic=False))
                continue
            # 普通文本段落:吞并直到空行或其它结构行
            i = self._consume_paragraph(lines, i)
            units.append(self._unit(lines, start, i, level=0, atomic=False))
        return units

    def _unit(self, lines: list[str], start: int, end: int, *, level: int, atomic: bool) -> dict:
        content = "\n".join(lines[start:end]).strip()
        if not content:
            content = "\n".join(lines[start:end])
        return {
            "content": content,
            "start": start,
            "end": end,
            "level": level,
            "atomic": atomic,
            "list_count": 0,
        }

    def _consume_fence(self, lines: list[str], i: int) -> int:
        marker = "```"
        if lines[i].lstrip().startswith("~~~"):
            marker = "~~~"
        i += 1
        while i < len(lines):
            if lines[i].strip().startswith(marker):
                return i + 1
            i += 1
        return i

    def _consume_table(self, lines: list[str], i: int) -> int:
        while i < len(lines) and self._line_kind(lines[i]) in {"table", "blank"}:
            if lines[i].strip():
                i += 1
            else:
                break
        return i

    def _consume_list(self, lines: list[str], i: int) -> int:
        # 连续列表项作为一个原子单元;空行结束该组。
        while i < len(lines) and self._line_kind(lines[i]) == "list":
            i += 1
        return i

    def _consume_continuous(self, lines: list[str], i: int, pred) -> int:
        while i < len(lines) and pred(lines[i]):
            i += 1
        return i

    def _consume_paragraph(self, lines: list[str], i: int) -> int:
        while i < len(lines):
            kind = self._line_kind(lines[i])
            if kind == "blank":
                break
            if kind in {"heading", "list", "table", "fence", "quote"}:
                break
            i += 1
        return i

    # ---- merge to target size ------------------------------------------

    @staticmethod
    def _is_pure_heading(unit: dict) -> bool:
        """没有自身正文内容的标题(章节/小节包裹标题)。"""
        return unit["level"] > 0 and "\n" not in unit["content"].strip()

    def _merge_units(self, units: list[dict]) -> list[dict]:
        """合并过短碎片,并把无正文的标题提升为其子块的前缀。

        两步:(1) 微小的非标题碎片折入前一块,使无微小块存活;
        (2) 没有自身正文的标题(如 ``## 第二章`` 这种子标题全是下级标题的
        章节包裹)变成「下一个块」的前导锚,而不是孤立成无用的短块。
        """
        merged: list[dict] = []
        for unit in units:
            if merged and len(unit["content"]) < self.min_chars and not self._is_pure_heading(unit):
                prev = merged[-1]
                prev["content"] = f"{prev['content']}\n{unit['content']}"
                prev["end"] = unit["end"]
            else:
                merged.append(dict(unit))
        result: list[dict] = []
        i = 0
        while i < len(merged):
            unit = merged[i]
            if self._is_pure_heading(unit) and i + 1 < len(merged):
                following = merged[i + 1]
                following["content"] = f"{unit['content']}\n{following['content']}"
                following["start"] = unit["start"]
                result.append(following)
                i += 2
            else:
                result.append(unit)
                i += 1
        return result

    @staticmethod
    def _line_offsets(lines: list[str]) -> list[int]:
        """每行首字符在原文中的绝对字符偏移。"""
        offsets: list[int] = []
        position = 0
        for line in lines:
            offsets.append(position)
            position += len(line) + 1  # +1 是连接行与行的 '\n'
        return offsets

    def _finalize(self, lines: list[str], offsets: list[int], units: list[dict]) -> list[ParsedDocumentChunk]:
        """把合并后的单元转成带精确、连续 locator 的块。"""
        chunks: list[ParsedDocumentChunk] = []
        for unit in units:
            first, last = unit["start"], unit["end"] - 1
            if first > last:
                continue
            region = "\n".join(lines[first : last + 1])
            if not region.strip():
                continue
            base = offsets[first]
            # 长正文切分,但结构化单元整体保留。
            pieces = self._split_for_size(region, atomic=unit["atomic"])
            cursor = base
            for piece in pieces:
                stripped = piece.strip()
                if not stripped:
                    cursor += len(piece)
                    continue
                leading = len(piece) - len(piece.lstrip())
                start = cursor + leading
                chunks.append(
                    ParsedDocumentChunk(
                        content=stripped,
                        locator={
                            "paragraph": first + 1,
                            "charStart": start,
                            "charEnd": start + len(stripped),
                        },
                    )
                )
                cursor += len(piece)
        return chunks

    @staticmethod
    def _looks_like_heading(block: str) -> bool:
        return block.lstrip().startswith("#")

    def _split_for_size(self, region: str, *, atomic: bool) -> list[str]:
        """返回按序拼合、恰好完整覆盖 ``region`` 的子串列表。

        原子单元(列表组/表格/代码围栏/引文)整体返回,不拆碎结构。长正文在
        空行或句末处切分,但保留每个分隔符,从而各片段能精确铺满原文(定位
        不失真)。标题块总是携带其后的正文,因此章节包裹标题绝不会被剥成孤立
        标题片段。
        """
        if atomic or len(region) <= self.target_chars:
            return [region]

        separators = list(re.finditer(r"\n[ \t]*\n", region))
        if not separators:
            return self._split_sentences(region)
        blocks: list[str] = []
        cursor = 0
        for match in separators:
            blocks.append(region[cursor : match.end()])
            cursor = match.end()
        if cursor < len(region):
            blocks.append(region[cursor:])

        pieces: list[str] = []
        i = 0
        n = len(blocks)
        while i < n:
            block = blocks[i]
            if self._looks_like_heading(block):
                # 标题是语义锚:持续吞并后续块(子标题与正文)直到大小上限,
                # 避免章节包裹标题被剥成孤立标题。
                acc = block
                i += 1
                while i < n and len(acc) + len(blocks[i]) <= self.target_chars * 1.5:
                    acc += blocks[i]
                    i += 1
                pieces.append(acc)
            else:
                acc = block
                i += 1
                while i < n and not self._looks_like_heading(blocks[i]) and len(acc) + len(blocks[i]) <= self.target_chars:
                    acc += blocks[i]
                    i += 1
                pieces.append(acc)
        return pieces or [region]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """仅在句末分隔符处切分,保留每个子串。"""
        segments: list[str] = []
        start = 0
        for match in re.finditer(r"[。！？；.!?;]", text):
            end = match.end()
            segments.append(text[start:end])
            start = end
        tail = text[start:]
        if tail:
            segments.append(tail)
        return segments or [text]



_EXTENSIONS = {
    ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv",
    ".json": "application/json", ".yaml": "application/yaml", ".yml": "application/yaml",
    ".xml": "application/xml", ".html": "text/html", ".htm": "text/html",
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword", ".xls": "application/vnd.ms-excel", ".ppt": "application/vnd.ms-powerpoint",
    ".odt": "application/vnd.oasis.opendocument.text", ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/tiff"}
_LEGACY_OFFICE = {".doc", ".xls", ".ppt", ".odt", ".ods", ".odp"}


def supported_extensions() -> list[str]:
    return sorted(_EXTENSIONS)


def detect_media_type(*, filename: str, claimed_media_type: str | None, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    media_type = _EXTENSIONS.get(extension)
    if media_type is None:
        raise DocumentExtractionError("SOURCE_MEDIA_UNSUPPORTED", "该文件格式暂不支持导入项目知识库")
    if not content:
        raise DocumentExtractionError("SOURCE_EMPTY", "资料内容不能为空")
    if media_type == "application/pdf" and not content.startswith(b"%PDF"):
        raise DocumentExtractionError("SOURCE_MEDIA_MISMATCH", "文件扩展名为 PDF，但文件签名不匹配")
    if media_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocumentExtractionError("SOURCE_MEDIA_MISMATCH", "PNG 文件签名不匹配")
    if media_type == "image/jpeg" and not content.startswith(b"\xff\xd8"):
        raise DocumentExtractionError("SOURCE_MEDIA_MISMATCH", "JPEG 文件签名不匹配")
    if extension in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}:
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(content)) as archive:
                names = set(archive.namelist())
                if extension == ".docx" and "word/document.xml" not in names:
                    raise ValueError
                if extension == ".xlsx" and "xl/workbook.xml" not in names:
                    raise ValueError
                if extension == ".pptx" and "ppt/presentation.xml" not in names:
                    raise ValueError
        except (zipfile.BadZipFile, ValueError) as exc:
            raise DocumentExtractionError("SOURCE_MEDIA_MISMATCH", "Office 文件结构不完整或与扩展名不匹配") from exc
    # Browser MIME is advisory only; the extension plus signature is authoritative.
    _ = claimed_media_type or mimetypes.guess_type(filename)[0]
    return media_type


def extract_document(*, content: bytes, filename: str, media_type: str, force_ocr: bool = False) -> ExtractedDocument:
    """Parse an uploaded source into locatable chunks.

    Plain and structured text are parsed locally (deterministic, low-cost).
    Binary formats (PDF, Office, images) go to the online MinerU precision API,
    which also provides forced OCR for scanned documents.
    """
    extension = Path(filename).suffix.lower()
    if media_type in {"text/plain", "text/markdown", "text/csv"}:
        return _extract_plain(content, media_type)
    if media_type in {"application/json", "application/yaml", "application/xml", "text/html"}:
        return _extract_structured(content, media_type)
    if media_type == "application/pdf" or media_type in _IMAGE_TYPES or extension in _LEGACY_OFFICE or extension in {".docx", ".xlsx", ".pptx"}:
        from app.infrastructure.mineru_client import parse_document_via_mineru

        return parse_document_via_mineru(content=content, filename=filename, settings=get_settings(), force_ocr=force_ocr)
    raise DocumentExtractionError("SOURCE_MEDIA_UNSUPPORTED", "该文件格式暂不支持导入项目知识库")


def _extract_plain(content: bytes, media_type: str) -> ExtractedDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentExtractionError("SOURCE_ENCODING_INVALID", "文本资料必须使用 UTF-8 编码") from exc
    chunks = MarkdownTextDocumentParser().parse(text)
    return ExtractedDocument(media_type, "plain-text-v2", chunks, text, {"textLength": len(text)})


def _extract_structured(content: bytes, media_type: str) -> ExtractedDocument:
    try:
        raw = content.decode("utf-8")
        if media_type == "application/json":
            normalized = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        elif media_type == "application/yaml":
            normalized = json.dumps(yaml.safe_load(raw), ensure_ascii=False, indent=2)
        elif media_type == "text/html":
            normalized = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
        else:
            normalized = raw
    except Exception as exc:
        raise DocumentExtractionError("SOURCE_PARSER_FAILED", "结构化文本无法安全解析") from exc
    chunks = _line_chunks(normalized, locator_key="line")
    return ExtractedDocument(media_type, "structured-text-v1", chunks, normalized, {"textLength": len(normalized)})


def _line_chunks(text: str, *, locator_key: str) -> list[ParsedDocumentChunk]:
    return [ParsedDocumentChunk(content=line.strip(), locator={locator_key: index}) for index, line in enumerate(text.splitlines(), start=1) if line.strip()]
