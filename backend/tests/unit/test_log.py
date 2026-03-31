"""結構化日誌模組的單元測試。"""

import json
import logging

import pytest

from ccas.log import JsonFormatter, RedactingFilter, configure_logging


class TestJsonFormatter:
    """JsonFormatter 輸出格式測試。"""

    def test_output_is_valid_json(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="ccas.parser.job",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="parse failed",
            args=None,
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert "timestamp" in parsed
        assert parsed["level"] == "WARNING"
        assert parsed["logger"] == "ccas.parser.job"
        assert parsed["message"] == "parse failed"

    def test_exception_included(self) -> None:
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error occurred",
            args=None,
            exc_info=exc_info,
        )
        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_message_with_args(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="processed %d items",
            args=(42,),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "processed 42 items"


class TestRedactingFilter:
    """RedactingFilter 機敏資訊遮罩測試。"""

    @pytest.fixture()
    def filt(self) -> RedactingFilter:
        return RedactingFilter()

    def _make_record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=None,
            exc_info=None,
        )

    def test_redacts_bearer_token(self, filt: RedactingFilter) -> None:
        record = self._make_record("Authorization: Bearer ya29.abc123xyz")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "ya29.abc123xyz" not in record.msg

    def test_redacts_access_token(self, filt: RedactingFilter) -> None:
        record = self._make_record('access_token=abc123secret')
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "abc123secret" not in record.msg

    def test_redacts_refresh_token(self, filt: RedactingFilter) -> None:
        record = self._make_record('refresh_token: "rt_secret_value"')
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "rt_secret_value" not in record.msg

    def test_redacts_password(self, filt: RedactingFilter) -> None:
        record = self._make_record("password=my_secret_pass")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "my_secret_pass" not in record.msg

    def test_redacts_credentials_path(self, filt: RedactingFilter) -> None:
        record = self._make_record("credentials_path=/home/user/.config/creds.json")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "/home/user/.config/creds.json" not in record.msg

    def test_normal_message_unchanged(self, filt: RedactingFilter) -> None:
        record = self._make_record("Processed 5 bills successfully")
        filt.filter(record)
        assert record.msg == "Processed 5 bills successfully"

    def test_redacts_in_tuple_args(self, filt: RedactingFilter) -> None:
        record = self._make_record("token is %s")
        record.args = ("bearer abc123",)
        filt.filter(record)
        assert record.args[0] == "bearer [REDACTED]"

    def test_redacts_in_dict_args(self, filt: RedactingFilter) -> None:
        record = self._make_record("%(key)s")
        record.args = {"key": "password=secret123"}
        filt.filter(record)
        assert "[REDACTED]" in record.args["key"]

    def test_filter_always_returns_true(self, filt: RedactingFilter) -> None:
        record = self._make_record("anything")
        assert filt.filter(record) is True


class TestConfigureLogging:
    """configure_logging 整合測試。"""

    @staticmethod
    def _mock_settings(
        level: str = "INFO", fmt: str = "json"
    ) -> object:
        from unittest.mock import MagicMock

        s = MagicMock()
        s.log_level = level
        s.log_format = fmt
        return s

    def test_sets_log_level(self) -> None:
        configure_logging(self._mock_settings("DEBUG"))  # type: ignore[arg-type]
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_json_format_uses_json_formatter(self) -> None:
        configure_logging(self._mock_settings())  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_text_format_uses_standard_formatter(self) -> None:
        configure_logging(self._mock_settings(fmt="text"))  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_redacting_filter_attached(self) -> None:
        configure_logging(self._mock_settings())  # type: ignore[arg-type]
        root = logging.getLogger()
        handler = root.handlers[0]
        filter_types = [type(f) for f in handler.filters]
        assert RedactingFilter in filter_types

    def test_idempotent_no_duplicate_handlers(self) -> None:
        s = self._mock_settings()
        configure_logging(s)  # type: ignore[arg-type]
        configure_logging(s)  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1
