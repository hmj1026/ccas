"""Router enum/string bridge helpers 的 fail-fast 行為測試。

``_scope_str`` / ``_channel_str`` 過去對未知值靜默回退預設值，
會掩蓋 DB 資料損壞；現在改為 raise HTTPException(500)（fail fast，
且經 FastAPI 以乾淨的 500 回應呈現而非未處理例外）。
"""

import pytest
from fastapi import HTTPException

from ccas.api.routers.budgets import _scope_str
from ccas.api.routers.reminders_settings import _channel_str
from ccas.storage.models import BudgetScope, ReminderChannel


class TestScopeStr:
    async def test_accepts_enum_member(self):
        assert _scope_str(BudgetScope.MONTHLY_CATEGORY) == "monthly_category"

    async def test_accepts_known_db_string(self):
        assert _scope_str("monthly_bank") == "monthly_bank"

    async def test_unknown_value_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _scope_str("weekly_total")
        assert exc_info.value.status_code == 500
        assert "unknown budget scope" in exc_info.value.detail


class TestChannelStr:
    async def test_accepts_enum_member(self):
        assert _channel_str(ReminderChannel.BOTH) == "both"

    async def test_accepts_known_db_string(self):
        assert _channel_str("ui_banner") == "ui_banner"

    async def test_unknown_value_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _channel_str("sms")
        assert exc_info.value.status_code == 500
        assert "unknown reminder channel" in exc_info.value.detail
