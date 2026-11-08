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


class FakeTransport:
    """Outbox 測試用 transport：記錄送出的訊息；可設定前 N 次呼叫失敗。"""

    def __init__(self, *, fail_times: int = 0) -> None:
        self.sent: list[str] = []
        self._fail_times = fail_times

    async def __call__(self, text: str) -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("telegram down")
        self.sent.append(text)
