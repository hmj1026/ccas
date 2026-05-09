"""Verify notify stage silently skips when Telegram credentials are empty.

Corresponds to user-guide §4: "留空則 notify 不發通知，其他階段不受影響".
"""

from unittest.mock import AsyncMock

import pytest

from ccas.bot.job import NotifySummary, run_notify_job


@pytest.fixture()
def _empty_telegram(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")


@pytest.fixture()
def _clear_settings_cache():
    from ccas.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("_empty_telegram", "_clear_settings_cache")
class TestNotifySkip:
    async def test_skips_when_chat_id_empty(self):
        session = AsyncMock()
        result = await run_notify_job(session)

        assert isinstance(result, NotifySummary)
        assert result.sent_count == 0
        assert result.failed_count == 0
        assert result.errors == []

    async def test_skips_when_bot_token_empty(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        from ccas.config import get_settings

        get_settings.cache_clear()

        session = AsyncMock()
        result = await run_notify_job(session)

        assert result.sent_count == 0
        assert result.failed_count == 0

    async def test_no_db_query_when_skipped(self):
        session = AsyncMock()
        await run_notify_job(session)
        session.execute.assert_not_called()
