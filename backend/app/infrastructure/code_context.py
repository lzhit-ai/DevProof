"""SHA-bound, Tree-sitter based minimal code-context collection.

This module never executes repository code.  It receives source bytes already read
from an immutable Git commit and produces CONTEXT_ONLY snippets for model input.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable


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
    from tree_sitter_language_pack import get_parser

    return get_parser(language)


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


def _imports(language: str, source: str) -> list[tuple[str, str]]:
    imports: list[tuple[str, str]] = []
    if language == "java":
        for target in re.findall(r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)\s*;", source):
            if target.endswith(".*"):
                continue
            imports.append((target.rsplit(".", 1)[-1], target))
    elif language == "python":
        for module, names in re.findall(r"(?m)^\s*from\s+([\w.]+)\s+import\s+([^\n#]+)", source):
            for name in names.split(","):
                value = name.strip().split(" as ")
                if value and value[0] != "*":
                    imports.append(((value[1] if len(value) > 1 else value[0]).strip(), f"{module}.{value[0].strip()}"))
        for module in re.findall(r"(?m)^\s*import\s+([\w.]+)", source):
            imports.append((module.rsplit(".", 1)[-1], module))
    else:
        for names, target in re.findall(r"(?m)^\s*import\s+(.+?)\s+from\s+['\"]([^'\"]+)['\"]", source):
            clean = names.strip()
            if clean.startswith("{") and clean.endswith("}"):
                for name in clean[1:-1].split(","):
                    value = name.strip().split(" as ")
                    if value and value[0]:
                        imports.append(((value[1] if len(value) > 1 else value[0]).strip(), target))
            elif clean.startswith("*") and " as " in clean:
                imports.append((clean.rsplit(" as ", 1)[-1].strip(), target))
            else:
                imports.append((clean.split(",", 1)[0].strip(), target))
    return [(name, target) for name, target in imports if _IDENTIFIER.fullmatch(name)]


def _resolve_import(*, language: str, importing_path: str, target: str, symbol: str, all_paths: set[str]) -> list[str]:
    normalized = target.replace(".", "/")
    if language == "java":
        suffix = f"/{normalized}.java"
        return [path for path in all_paths if path == f"{normalized}.java" or path.endswith(suffix)]
    if language == "python":
        module = target.rsplit(".", 1)[0] if target.rsplit(".", 1)[-1] == symbol else target
        normalized = module.replace(".", "/")
        candidates = {f"{normalized}.py", f"{normalized}/__init__.py"}
        return [path for path in all_paths if path in candidates or any(path.endswith(f"/{item}") for item in candidates)]
    if not target.startswith("."):
        return []
    base = posixpath.dirname(importing_path)
    stem = posixpath.normpath(posixpath.join(base, target))
    candidates = {stem + suffix for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue", ".mts", ".cts")}
    candidates.update({f"{stem}/index{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx", ".vue")})
    return [path for path in all_paths if path in candidates]


def _context_id(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"ctx-{hashlib.sha256(raw).hexdigest()[:20]}"


def _first_added_line(hunk: dict) -> int | None:
    """Return the first real added line, not merely the start of a mixed hunk."""
    line = hunk.get("new_start")
    if not isinstance(line, int) or line <= 0:
        return None
    for item in str(hunk.get("payload", "")).splitlines():
        if item.startswith("+") and not item.startswith("+++"):
            return line
        if not item.startswith("-"):
            line += 1
    return hunk.get("new_start")


def enrich_symbol_context(
    bundle: dict,
    *,
    target_sha: str,
    read_blob: Callable[[str, str], bytes],
    list_paths: Callable[[str], list[str]],
    max_related_symbols: int,
) -> dict:
    """Append deterministic enclosing and one-hop import contexts to a V1 bundle."""
    contexts: list[dict] = []
    context_candidates: list[dict] = []
    skipped: list[dict] = []
    resolved = 0
    ambiguous = 0
    try:
        all_paths = set(list_paths(target_sha))
    except Exception:
        all_paths = set()
        skipped.append({"reasonCode": "SYMBOL_INDEX_UNAVAILABLE"})

    seen: set[str] = set()

    def append_context(*, path: str, language: str, relation: str, payload: dict) -> bool:
        nonlocal resolved
        identity = {"path": path, "symbol": payload["symbol"], "startLine": payload["startLine"], "endLine": payload["endLine"], "relation": relation, "targetSha": target_sha}
        context_id = _context_id(identity)
        if context_id in seen:
            return True
        if len(contexts) >= max_related_symbols:
            skipped.append({"path": path, "symbol": payload["symbol"], "reasonCode": "RELATED_SYMBOL_LIMIT"})
            return False
        seen.add(context_id)
        contexts.append({
            "contextId": context_id,
            "path": path,
            "commitSha": target_sha,
            "language": language,
            "symbol": payload["symbol"],
            "symbolKind": payload["symbolKind"],
            "kind": "SYMBOL",
            "relation": relation,
            "startLine": payload["startLine"],
            "endLine": payload["endLine"],
            "content": payload["content"],
            "contentHash": f"sha256:{hashlib.sha256(payload['content'].encode('utf-8')).hexdigest()}",
            "evidenceRole": "CONTEXT_ONLY",
        })
        resolved += 1
        return True

    for file in bundle.get("files", []):
        path = str(file.get("path", ""))
        target_source = file.get("target_context")
        if file.get("context_state") != "COMPLETE" or not isinstance(target_source, str):
            continue
        parsed = _parse_source(path, target_source)
        if parsed is None:
            skipped.append({"path": path, "reasonCode": "PARSER_UNSUPPORTED"})
            continue
        for hunk in file.get("hunks", []):
            line = _first_added_line(hunk)
            if line is None:
                continue
            enclosing = _symbol_at_line(parsed, line)
            if enclosing is None:
                skipped.append({"path": path, "hunk": hunk.get("header"), "reasonCode": "ENCLOSING_SYMBOL_NOT_FOUND"})
                continue
            append_context(path=path, language=parsed.language, relation="CHANGED_SYMBOL", payload=enclosing)
            for imported_name, import_target in _imports(parsed.language, target_source):
                if not re.search(rf"\b{re.escape(imported_name)}\b", enclosing["content"]):
                    continue
                paths = _resolve_import(language=parsed.language, importing_path=path, target=import_target, symbol=imported_name, all_paths=all_paths)
                if len(paths) != 1:
                    ambiguous += int(bool(paths))
                    skipped.append({"path": path, "symbol": imported_name, "reasonCode": "SYMBOL_AMBIGUOUS" if paths else "SYMBOL_NOT_FOUND"})
                    continue
                related_path = paths[0]
                candidate_identity = {
                    "fromPath": path,
                    "fromSymbol": enclosing["symbol"],
                    "symbol": imported_name,
                    "relation": "DIRECT_IMPORT",
                    "path": related_path,
                    "targetSha": target_sha,
                }
                context_candidates.append({
                    "candidateId": _context_id(candidate_identity),
                    **candidate_identity,
                })
                try:
                    related_source = read_blob(target_sha, related_path).decode("utf-8", errors="replace")
                except Exception:
                    skipped.append({"path": related_path, "symbol": imported_name, "reasonCode": "GIT_CONTEXT_UNAVAILABLE"})
                    continue
                related = _parse_source(related_path, related_source)
                if related is None:
                    skipped.append({"path": related_path, "symbol": imported_name, "reasonCode": "PARSER_UNSUPPORTED"})
                    continue
                symbol = _symbol_named(related, imported_name)
                if symbol is None:
                    skipped.append({"path": related_path, "symbol": imported_name, "reasonCode": "SYMBOL_DEFINITION_NOT_FOUND"})
                    continue
                append_context(path=related_path, language=related.language, relation="DIRECT_IMPORT", payload=symbol)

    return {
        **bundle,
        "schemaVersion": "code-change-bundle-v2",
        "contexts": contexts,
        "contextCandidates": context_candidates,
        "coverage": {
            **(bundle.get("coverage") or {}),
            "contextSchemaVersion": "v2",
            "relatedContextCount": len(contexts),
            "resolvedSymbols": resolved,
            "ambiguousSymbols": ambiguous,
            "contextSkipped": skipped,
        },
    }
