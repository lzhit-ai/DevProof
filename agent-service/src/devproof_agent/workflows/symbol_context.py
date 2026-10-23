"""SHA-bound, Tree-sitter based minimal code-context collection.

This module never executes repository code.  It receives source bytes already read
from an immutable Git commit and produces CONTEXT_ONLY snippets for model input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


_DECLARATION_TYPES = {
    "java": {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration", "method_declaration", "constructor_declaration", "annotation_type_declaration"},
    "python": {"class_definition", "function_definition"},
    "javascript": {"class_declaration", "function_declaration", "method_definition", "generator_function_declaration", "arrow_function"},
    "typescript": {"class_declaration", "function_declaration", "method_definition", "generator_function_declaration", "arrow_function", "interface_declaration", "type_alias_declaration", "enum_declaration"},
    "tsx": {"class_declaration", "function_declaration", "method_definition", "generator_function_declaration", "arrow_function", "interface_declaration", "type_alias_declaration", "enum_declaration"},
}
_SCRIPT_TAG = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_LANG_ATTR = re.compile(r"\blang\s*=\s*['\"](?P<lang>[^'\"]+)['\"]", re.IGNORECASE)
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


@dataclass(frozen=True)
class ParsedSource:
    language: str
    source: str
    line_offset: int = 0


def detect_language(path: str, source: str = "") -> str | None:
    lower = path.casefold()
    if lower.endswith(".java"):
        return "java"
    if lower.endswith(".py"):
        return "python"
    if lower.endswith((".ts", ".mts", ".cts")):
        return "typescript"
    if lower.endswith(".tsx"):
        return "tsx"
    if lower.endswith((".js", ".mjs", ".cjs", ".jsx")):
        return "javascript"
    if lower.endswith(".vue"):
        match = _SCRIPT_TAG.search(source)
        if not match:
            return None
        language_match = _LANG_ATTR.search(match.group("attrs"))
        lang = language_match.group("lang").casefold() if language_match else ""
        return "typescript" if lang in {"ts", "tsx"} else "javascript"
    return None


def _parse_source(path: str, source: str) -> ParsedSource | None:
    language = detect_language(path, source)
    if language is None:
        return None
    if path.casefold().endswith(".vue"):
        match = _SCRIPT_TAG.search(source)
        if match is None:
            return None
        return ParsedSource(language=language, source=match.group("body"), line_offset=source[:match.start("body")].count("\n"))
    return ParsedSource(language=language, source=source)


@lru_cache(maxsize=8)
def _parser(language: str):
    """Load only the requested grammar. Import errors are handled as coverage, not failures."""
    from devproof_agent.syntax import parser
    return parser(language)


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _node_name(node, source_bytes: bytes) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return source_bytes[named.start_byte:named.end_byte].decode("utf-8", errors="replace")
    for child in node.children:
        if child.type in {"identifier", "type_identifier", "property_identifier"}:
            return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return None


def _symbol_at_line(parsed: ParsedSource, line: int) -> dict | None:
    local_line = line - parsed.line_offset
    if local_line < 1:
        return None
    try:
        tree = _parser(parsed.language).parse(parsed.source.encode("utf-8"))
    except Exception:
        return None
    source_bytes = parsed.source.encode("utf-8")
    candidates: list[tuple[int, dict]] = []
    for node in _walk(tree.root_node):
        if node.type not in _DECLARATION_TYPES[parsed.language]:
            continue
        start, end = node.start_point.row + 1, node.end_point.row + 1
        if start <= local_line <= end:
            candidates.append((node.end_byte - node.start_byte, {
                "symbol": _node_name(node, source_bytes) or node.type,
                "symbolKind": node.type,
                "startLine": start + parsed.line_offset,
                "endLine": end + parsed.line_offset,
                "content": source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            }))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _symbol_named(parsed: ParsedSource, symbol: str) -> dict | None:
    try:
        tree = _parser(parsed.language).parse(parsed.source.encode("utf-8"))
    except Exception:
        return None
    source_bytes = parsed.source.encode("utf-8")
    for node in _walk(tree.root_node):
        if node.type not in _DECLARATION_TYPES[parsed.language]:
            continue
        if _node_name(node, source_bytes) == symbol:
            return {
                "symbol": symbol,
                "symbolKind": node.type,
                "startLine": node.start_point.row + 1 + parsed.line_offset,
                "endLine": node.end_point.row + 1 + parsed.line_offset,
                "content": source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            }
    return None


def extract_symbol_context(path: str, source: str, symbol: str) -> dict | None:
    """Extract one named declaration from source already read at a frozen SHA."""
    parsed = _parse_source(path, source)
    return _symbol_named(parsed, symbol) if parsed is not None else None
