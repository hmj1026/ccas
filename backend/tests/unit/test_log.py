"""結構化日誌模組的單元測試。"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from ccas.log import JsonFormatter, RedactingFilter, configure_logging


def _make_mock_settings(
    *,
    level: str = "INFO",
    fmt: str = "json",
    log_dir: str = "",
    log_file_max_bytes: int = 10_485_760,
    log_file_backup_count: int = 5,
    log_file_prefix: str = "ccas",
) -> object:
    """建立模擬 Settings 物件供 configure_logging 測試使用。"""
    from unittest.mock import MagicMock

    s = MagicMock()
    s.log_level = level
    s.log_format = fmt
    s.log_dir = log_dir
    s.log_file_max_bytes = log_file_max_bytes
    s.log_file_backup_count = log_file_backup_count
    s.log_file_prefix = log_file_prefix
    return s


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

    def test_redacts_anthropic_key_in_bare_message(self, filt: RedactingFilter) -> None:
        """Anthropic SDK exceptions can echo keys without an ``api_key=``
        prefix; the bare-prefix pattern must catch these defensively."""
        record = self._make_record(
            "anthropic API error: invalid key sk-ant-api03-abc_DEF-123xyz"
        )
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "abc_DEF-123xyz" not in record.msg
        assert "sk-ant-api03-" in record.msg  # prefix kept, suffix redacted

    def test_redacts_bearer_token(self, filt: RedactingFilter) -> None:
        record = self._make_record("Authorization: Bearer ya29.abc123xyz")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "ya29.abc123xyz" not in record.msg

    def test_redacts_access_token(self, filt: RedactingFilter) -> None:
        record = self._make_record("access_token=abc123secret")
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

    def test_redacts_national_id(self, filt: RedactingFilter) -> None:
        record = self._make_record('national_id="A123456789"')
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "A123456789" not in record.msg

    def test_redacts_nid_short_form(self, filt: RedactingFilter) -> None:
        record = self._make_record("nid=B987654321")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "B987654321" not in record.msg

    def test_redacts_roc_birthday(self, filt: RedactingFilter) -> None:
        record = self._make_record("roc_birthday=0881010")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "0881010" not in record.msg

    def test_redacts_card_last4(self, filt: RedactingFilter) -> None:
        record = self._make_record('card_last4="1234"')
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        # Only the value after the key is redacted
        assert 'card_last4="1234"' not in record.msg

    def test_redacts_chat_id(self, filt: RedactingFilter) -> None:
        record = self._make_record("chat_id=123456789")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "123456789" not in record.msg

    def test_redacts_telegram_chat_id(self, filt: RedactingFilter) -> None:
        record = self._make_record('telegram_chat_id: "-1001234567890"')
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "1001234567890" not in record.msg

    def test_redacts_jwt_field(self, filt: RedactingFilter) -> None:
        record = self._make_record('jwt="eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM"')
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "SflKxwRJSM" not in record.msg

    def test_redacts_authorization_raw_jwt(self, filt: RedactingFilter) -> None:
        """FUBON uses a raw JWT in Authorization (no Bearer prefix)."""
        record = self._make_record("Authorization=eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "SflKxwRJSM" not in record.msg

    def test_redacts_session_cookie_in_cookie_header(
        self, filt: RedactingFilter
    ) -> None:
        record = self._make_record(
            "request headers: Cookie: ccas_session=1.1781102450.deadbeefcafe"
        )
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "deadbeefcafe" not in record.msg
        assert "ccas_session=" in record.msg  # cookie name kept, value redacted

    def test_redacts_session_cookie_in_set_cookie_header(
        self, filt: RedactingFilter
    ) -> None:
        record = self._make_record(
            "Set-Cookie: ccas_session=1.1781102450.deadbeefcafe;"
            " HttpOnly; Path=/; SameSite=lax"
        )
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "deadbeefcafe" not in record.msg
        # Attributes after ";" stay readable for debugging.
        assert "HttpOnly" in record.msg
        assert "SameSite=lax" in record.msg

    def test_redacts_session_token_with_custom_cookie_name(
        self, filt: RedactingFilter
    ) -> None:
        """結構式 fallback：cookie 名稱被覆寫時，token 值仍須被遮罩。"""
        token = "3.1781102450." + "a1" * 32
        record = self._make_record(f"Cookie: my_custom_session={token}")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert token not in record.msg

    def test_redacts_pdf_password_env_assignment(self, filt: RedactingFilter) -> None:
        """Bank-suffixed env names (PDF_PASSWORD_CTBC=...) lack ":"/"="
        right after "password", so the generic rule misses them."""
        record = self._make_record("env dump: PDF_PASSWORD_CTBC=secret-pass-123")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "secret-pass-123" not in record.msg
        assert "PDF_PASSWORD_CTBC" in record.msg  # key kept, value redacted

    def test_redacts_pdf_password_with_spaces_and_case(
        self, filt: RedactingFilter
    ) -> None:
        record = self._make_record("pdf_password_esun = TopSecret!9")
        filt.filter(record)
        assert "[REDACTED]" in record.msg
        assert "TopSecret!9" not in record.msg

    def test_pii_field_in_dict_args(self, filt: RedactingFilter) -> None:
        record = self._make_record("%(key)s")
        record.args = {"key": "national_id=A123456789"}
        filt.filter(record)
        assert isinstance(record.args, dict)
        assert "[REDACTED]" in record.args["key"]
        assert "A123456789" not in record.args["key"]


class TestConfigureLogging:
    """configure_logging 整合測試。"""

    def test_sets_log_level(self) -> None:
        configure_logging(_make_mock_settings(level="DEBUG"))  # type: ignore[arg-type]
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_json_format_uses_json_formatter(self) -> None:
        configure_logging(_make_mock_settings())  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_text_format_uses_standard_formatter(self) -> None:
        configure_logging(_make_mock_settings(fmt="text"))  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_redacting_filter_attached(self) -> None:
        configure_logging(_make_mock_settings())  # type: ignore[arg-type]
        root = logging.getLogger()
        handler = root.handlers[0]
        filter_types = [type(f) for f in handler.filters]
        assert RedactingFilter in filter_types

    def test_idempotent_no_duplicate_handlers(self) -> None:
        s = _make_mock_settings()
        configure_logging(s)  # type: ignore[arg-type]
        configure_logging(s)  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1


class TestFileHandler:
    """RotatingFileHandler 相關測試。"""

    def test_no_file_handler_when_log_dir_empty(self) -> None:
        """5.1: log_dir 為空時不建立 file handler。"""
        configure_logging(_make_mock_settings(log_dir=""))  # type: ignore[arg-type]
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)
        assert not isinstance(root.handlers[0], RotatingFileHandler)

    def test_file_handler_created_when_log_dir_set(self, tmp_path: Path) -> None:
        """5.2: log_dir 非空時建立 RotatingFileHandler 並正確設定參數。"""
        configure_logging(
            _make_mock_settings(
                log_dir=str(tmp_path),
                log_file_max_bytes=5_000_000,
                log_file_backup_count=3,
            )  # type: ignore[arg-type]
        )
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        fh = file_handlers[0]
        assert fh.maxBytes == 5_000_000
        assert fh.backupCount == 3

    def test_file_handler_has_redacting_filter(self, tmp_path: Path) -> None:
        """5.3: file handler 掛載 RedactingFilter。"""
        configure_logging(
            _make_mock_settings(log_dir=str(tmp_path))  # type: ignore[arg-type]
        )
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        filter_types = [type(f) for f in file_handlers[0].filters]
        assert RedactingFilter in filter_types

    def test_log_dir_created_if_not_exists(self, tmp_path: Path) -> None:
        """5.4: 日誌目錄不存在時自動建立。"""
        new_dir = tmp_path / "nested" / "logs"
        assert not new_dir.exists()
        configure_logging(
            _make_mock_settings(log_dir=str(new_dir))  # type: ignore[arg-type]
        )
        assert new_dir.exists()

    def test_log_file_prefix_affects_filename(self, tmp_path: Path) -> None:
        """5.5: log_file_prefix 參數影響檔名。"""
        configure_logging(
            _make_mock_settings(
                log_dir=str(tmp_path),
                log_file_prefix="ccas-worker",
            )  # type: ignore[arg-type]
        )
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename.endswith("ccas-worker.log")

    def test_file_handler_idempotent_when_log_dir_set(self, tmp_path: Path) -> None:
        """連續呼叫兩次 configure_logging 時只保留一個 RotatingFileHandler。"""
        s = _make_mock_settings(log_dir=str(tmp_path))
        configure_logging(s)  # type: ignore[arg-type]
        configure_logging(s)  # type: ignore[arg-type]
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1

    def test_file_handler_uses_json_formatter(self, tmp_path: Path) -> None:
        """file handler 繼承與 StreamHandler 相同的 formatter 類型。"""
        configure_logging(
            _make_mock_settings(log_dir=str(tmp_path), fmt="json")  # type: ignore[arg-type]
        )
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert isinstance(file_handlers[0].formatter, JsonFormatter)

    def test_file_handler_uses_text_formatter(self, tmp_path: Path) -> None:
        """log_format=text 時 file handler 使用標準 Formatter。"""
        configure_logging(
            _make_mock_settings(log_dir=str(tmp_path), fmt="text")  # type: ignore[arg-type]
        )
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert not isinstance(file_handlers[0].formatter, JsonFormatter)
