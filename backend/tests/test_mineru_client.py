"""Regression coverage for the bounded MinerU online parsing client."""

import io
import unittest
import zipfile
from unittest import mock

from app.core.config import Settings
from app.infrastructure.mineru_client import (
    MineruParseError,
    _read_markdown_from_zip,
    parse_document_via_mineru,
)


def _settings() -> Settings:
    return Settings(
        mineru_api_token="test-token",
        mineru_api_base_url="https://mineru.net",
        mineru_model_version="pipeline",
        mineru_force_ocr=True,
        mineru_language="ch",
        mineru_timeout_seconds=60,
        mineru_poll_interval_seconds=1,
        mineru_result_max_bytes=10 * 1024 * 1024,
        jwt_secret="x" * 48,
    )


def _zip_with(full_md: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("full.md", full_md)
    return buffer.getvalue()


class MineruParseTests(unittest.TestCase):
    def test_parses_document_end_to_end(self) -> None:
        submit = {
            "code": 0,
            "data": {"batch_id": "batch-1", "file_urls": ["https://oss/api-upload/example"]},
        }
        upload_calls: list[tuple[str, bytes]] = []
        poll_responses = iter(
            [
                {"code": 0, "data": {"extract_result": [{"state": "running"}]}},
                {"code": 0, "data": {"extract_result": [{"state": "done", "full_zip_url": "https://cdn/full.zip"}]}},
            ]
        )
        zip_bytes = _zip_with("# 标题\n\n这是第一段示例文本。\n\n- 列表项")
        with mock.patch("app.infrastructure.mineru_client._json_post", return_value=submit) as submit_mock, \
             mock.patch("app.infrastructure.mineru_client._upload_bytes", side_effect=lambda url, content, timeout: upload_calls.append((url, content))) as upload_mock, \
             mock.patch("app.infrastructure.mineru_client._json_get", side_effect=lambda *_a, **_k: next(poll_responses)) as get_mock, \
             mock.patch("app.infrastructure.mineru_client._fetch_bytes", return_value=zip_bytes) as fetch_mock, \
             mock.patch("app.infrastructure.mineru_client.time.sleep") as sleep_mock:
            result = parse_document_via_mineru(content=b"%PDF-fake", filename="demo.pdf", settings=_settings())

        self.assertEqual(result.parser_version, "mineru-v4")
        self.assertEqual(result.normalized_text, "# 标题\n\n这是第一段示例文本。\n\n- 列表项")
        self.assertTrue(result.chunks)
        submit_payload = submit_mock.call_args.kwargs["payload"]
        self.assertEqual(submit_payload["files"][0]["name"], "demo.pdf")
        self.assertTrue(submit_payload["files"][0]["is_ocr"])
        self.assertEqual(submit_payload["model_version"], "pipeline")
        upload_mock.assert_called_once()
        self.assertEqual(upload_calls[0][1], b"%PDF-fake")
        self.assertEqual(fetch_mock.call_args.args[0], "https://cdn/full.zip")
        sleep_mock.assert_called_once()

    def test_missing_token_raises(self) -> None:
        settings = _settings()
        settings.mineru_api_token = None
        with self.assertRaisesRegex(MineruParseError, "MINERU_API_TOKEN"):
            parse_document_via_mineru(content=b"x", filename="a.pdf", settings=settings)

    def test_submit_rejection_maps_to_stable_error(self) -> None:
        with mock.patch("app.infrastructure.mineru_client._json_post", return_value={"code": -60002, "msg": "检测文件类型失败"}):
            with self.assertRaisesRegex(MineruParseError, "MinerU 拒绝解析任务"):
                parse_document_via_mineru(
                    content=b"x",
                    filename="a.pdf",
                    settings=_settings(),
                )

    def test_failed_state_maps_to_error(self) -> None:
        submit = {"code": 0, "data": {"batch_id": "b", "file_urls": ["https://oss/u"]}}
        polls = iter([{"code": 0, "data": {"extract_result": [{"state": "failed", "err_msg": "文件格式不支持"}]}}])
        with mock.patch("app.infrastructure.mineru_client._json_post", return_value=submit), \
             mock.patch("app.infrastructure.mineru_client._upload_bytes"), \
             mock.patch("app.infrastructure.mineru_client._json_get", side_effect=lambda *_a, **_k: next(polls)):
            with self.assertRaisesRegex(MineruParseError, "MinerU 解析失败") as ctx:
                parse_document_via_mineru(content=b"x", filename="a.pdf", settings=_settings())
        self.assertIn("文件格式不支持", str(ctx.exception))

    def test_zip_without_markdown_is_rejected(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("other.txt", "nope")
        with self.assertRaisesRegex(MineruParseError, "MinerU 解析结果缺少 Markdown 文件"):
            _read_markdown_from_zip(buffer.getvalue())

    def test_read_markdown_from_zip(self) -> None:
        self.assertEqual(_read_markdown_from_zip(_zip_with("hello")), "hello")


if __name__ == "__main__":
    unittest.main()
