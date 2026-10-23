from app.application.services.code_review_service import plan_code_review
from app.infrastructure.code_context import detect_language, enrich_symbol_context, extract_symbol_context


def _bundle(path: str, source: str, line: int = 2) -> dict:
    return {
        "schemaVersion": "code-change-bundle-v1",
        "files": [{
            "path": path,
            "context_state": "COMPLETE",
            "target_context": source,
            "hunks": [{"header": "@@ -1 +1 @@", "new_start": line}],
        }],
        "coverage": {},
    }


def test_java_context_extracts_changed_method_and_direct_import() -> None:
    bundle = enrich_symbol_context(
        _bundle(
            "src/PaymentService.java",
            "import com.example.config.RetryPolicy;\nclass PaymentService { void pay() { RetryPolicy.run(); } }\n",
        ),
        target_sha="a" * 40,
        list_paths=lambda _: ["src/com/example/config/RetryPolicy.java"],
        read_blob=lambda *_: b"package com.example.config; public class RetryPolicy { public static void run() {} }",
        max_related_symbols=8,
    )
    assert bundle["schemaVersion"] == "code-change-bundle-v2"
    assert {item["relation"] for item in bundle["contexts"]} == {"CHANGED_SYMBOL", "DIRECT_IMPORT"}
    assert bundle["contexts"][0]["evidenceRole"] == "CONTEXT_ONLY"
    assert bundle["contextCandidates"][0]["path"] == "src/com/example/config/RetryPolicy.java"


def test_python_and_typescript_context_resolve_direct_imports() -> None:
    python_bundle = enrich_symbol_context(
        _bundle("app/payment.py", "from app.retry import RetryPolicy\ndef pay():\n    return RetryPolicy.run()\n", line=2),
        target_sha="b" * 40,
        list_paths=lambda _: ["app/retry.py"],
        read_blob=lambda *_: b"class RetryPolicy:\n    @staticmethod\n    def run():\n        return True\n",
        max_related_symbols=8,
    )
    typescript_bundle = enrich_symbol_context(
        _bundle("src/payment.ts", "import { RetryPolicy } from './retryPolicy';\nexport function pay() { return RetryPolicy.run(); }\n"),
        target_sha="c" * 40,
        list_paths=lambda _: ["src/retryPolicy.ts"],
        read_blob=lambda *_: b"export class RetryPolicy { static run() { return true; } }",
        max_related_symbols=8,
    )
    assert any(item["symbol"] == "RetryPolicy" for item in python_bundle["contexts"])
    assert any(item["symbol"] == "RetryPolicy" for item in typescript_bundle["contexts"])


def test_context_builder_never_guesses_ambiguous_imports() -> None:
    bundle = enrich_symbol_context(
        _bundle("src/payment.ts", "import { RetryPolicy } from './retryPolicy';\nexport function pay() { return RetryPolicy.run(); }\n"),
        target_sha="d" * 40,
        list_paths=lambda _: ["src/retryPolicy.ts", "src/retryPolicy.js"],
        read_blob=lambda *_: b"export class RetryPolicy {}",
        max_related_symbols=8,
    )
    assert bundle["coverage"]["ambiguousSymbols"] == 1
    assert not any(item["relation"] == "DIRECT_IMPORT" for item in bundle["contexts"])


def test_vue_script_and_planner_keep_related_context_as_context_only() -> None:
    assert detect_language("Qr.vue", "<script setup lang=\"ts\">const ok = true</script>") == "typescript"
    extracted = extract_symbol_context("src/payment.ts", "export function pay() { return true; }", "pay")
    assert extracted is not None and extracted["symbol"] == "pay"
    changes, _ = plan_code_review(
        bundle={
            "files": [{"path": "a.py", "binary": False, "context_state": "COMPLETE", "base_context": "", "target_context": "", "hunks": [{"header": "@@ -1 +1 @@", "old_start": 1, "old_end": 1, "new_start": 1, "new_end": 1, "payload": "+x"}]}],
            "contexts": [{"contextId": "ctx-1", "path": "retry.py", "symbol": "RetryPolicy", "symbolKind": "class_definition", "relation": "DIRECT_IMPORT", "startLine": 1, "endLine": 2, "content": "class RetryPolicy: pass"}],
        },
        evidence_by_locator={("a.py", "@@ -1 +1 @@"): "evidence-1"},
        claims=[],
        char_budget=5_000,
    )
    assert changes[0]["relatedContexts"][0]["evidenceRole"] == "CONTEXT_ONLY"
