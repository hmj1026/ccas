"""Verify Settings defaults match user-guide §2 documented values."""

import pytest
from pydantic import ValidationError

from ccas.config import Settings


@pytest.fixture()
def settings(monkeypatch):
    """Minimal Settings with only required fields."""
    monkeypatch.setenv("API_TOKEN", "test-token")
    return Settings(_env_file=None)


class TestDocumentedDefaults:
    """Each test maps to one row in user-guide §2 optional env vars table."""

    def test_database_url_default(self, settings):
        assert "sqlite+aiosqlite:///" in settings.database_url
        assert settings.database_url.endswith("data/ccas.db")

    def test_api_host_default(self, settings):
        assert settings.api_host == "0.0.0.0"

    def test_api_port_default(self, settings):
        assert settings.api_port == 8000

    def test_frontend_origins_default(self, settings):
        origins = settings.get_frontend_origins()
        assert "http://127.0.0.1:5173" in origins
        assert "http://localhost:5173" in origins

    def test_redis_url_default(self, settings):
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_log_level_default(self, settings):
        assert settings.log_level == "INFO"

    def test_log_format_default(self, settings):
        assert settings.log_format == "json"

    def test_session_cookie_name_default(self, settings):
        assert settings.api_session_cookie_name == "ccas_session"

    def test_session_max_age_default(self, settings):
        assert settings.api_session_max_age == 43200

    def test_cookie_secure_default(self, settings):
        # Secure-by-default: cookie only sent over TLS unless explicitly opted out.
        assert settings.api_cookie_secure is True

    def test_cookie_secure_opt_out(self, monkeypatch):
        """HTTP-only local dev can opt out via API_COOKIE_SECURE=false."""
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("API_COOKIE_SECURE", "false")
        s = Settings(_env_file=None)
        assert s.api_cookie_secure is False

    def test_fubon_captcha_max_retries_default(self, settings):
        assert settings.fubon_captcha_max_retries == 7

    def test_fubon_captcha_fallback_llm_default(self, settings):
        assert settings.fubon_captcha_fallback_llm is False

    def test_fubon_manual_staging_dir_default(self, settings):
        assert settings.fubon_manual_staging_dir.endswith("manual-staging/FUBON")


class TestRequiredFields:
    def test_api_token_required(self, monkeypatch):
        monkeypatch.delenv("API_TOKEN", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestOptionalFieldsEmpty:
    def test_telegram_bot_token_defaults_empty(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        s = Settings(_env_file=None)
        assert s.telegram_bot_token.get_secret_value() == ""

    def test_telegram_chat_id_defaults_empty(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        s = Settings(_env_file=None)
        assert s.telegram_chat_id == ""

    def test_telegram_allowed_chat_ids_defaults_empty(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
        s = Settings(_env_file=None)
        assert s.telegram_allowed_chat_ids == ""


class TestTelegramChatIdValidator:
    """TELEGRAM_CHAT_ID 非空時必須可解析為 int（負數群組 ID 合法）。"""

    def test_numeric_chat_id_accepted(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        s = Settings(_env_file=None)
        assert s.telegram_chat_id == "12345"

    def test_negative_group_chat_id_accepted(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "-12345")
        s = Settings(_env_file=None)
        assert s.telegram_chat_id == "-12345"

    def test_whitespace_is_stripped(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "  12345  ")
        s = Settings(_env_file=None)
        assert s.telegram_chat_id == "12345"

    def test_whitespace_only_normalizes_to_empty(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "   ")
        s = Settings(_env_file=None)
        assert s.telegram_chat_id == ""

    def test_non_numeric_chat_id_rejected(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "not-a-chat-id")
        with pytest.raises(ValidationError, match="TELEGRAM_CHAT_ID"):
            Settings(_env_file=None)
