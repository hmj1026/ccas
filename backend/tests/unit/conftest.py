"""單元測試共用 Fixtures。

單元測試不依賴 Yii/DB/外部服務，僅測試純邏輯。
"""

from collections.abc import Generator

import pytest

from ccas.config import get_settings


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Provide required Settings env vars for all unit tests.

    Prevents ValidationError when Settings fields telegram_bot_token,
    telegram_chat_id, or api_token are not set in the test environment.
    Individual tests may override these values via their own monkeypatch calls.
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.setenv("API_TOKEN", "test-api-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
