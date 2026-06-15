"""Bot wrapper / handler 錯誤處理單元測試（Stage 3 P2）。

驗證：
- handler 拋例外時，_with_auth_and_session 仍記錄 error 並回覆使用者錯誤訊息
- 未授權 chat 永遠不會收到錯誤回覆（授權檢查在 try 之外）
- 回覆本身失敗只記 warning，不再往外拋
- handle_paid 即使回覆失敗仍已 commit（DB 一致性優先）
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.bot.app import _with_auth_and_session
from ccas.bot.handlers import handle_paid

ALLOWED = frozenset({123})


def _make_update(chat_id: int | None = 123) -> MagicMock:
    update = MagicMock()
    if chat_id is None:
        update.effective_chat = None
    else:
        update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    return update


def _session_factory(session: MagicMock):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.mark.asyncio
class TestWrapperErrorHandling:
    async def test_handler_exception_logs_and_replies(self, caplog):
        """handler 拋例外 → 記 error log 且回覆使用者錯誤訊息。"""
        update = _make_update()
        context = MagicMock()
        session = MagicMock()

        async def boom(_u, _c, _s):
            raise RuntimeError("db down")

        wrapped = _with_auth_and_session(boom, ALLOWED, _session_factory(session))

        with caplog.at_level("ERROR"):
            await wrapped(update, context)

        update.message.reply_text.assert_awaited_once_with("發生錯誤，請稍後再試。")
        assert any("Bot handler error" in r.message for r in caplog.records)

    async def test_unauthorized_chat_gets_no_error_reply(self):
        """未授權 chat：handler 不執行、也絕不回覆錯誤訊息。"""
        update = _make_update(chat_id=999)  # not in ALLOWED
        context = MagicMock()
        session = MagicMock()
        handler = AsyncMock()

        wrapped = _with_auth_and_session(handler, ALLOWED, _session_factory(session))

        await wrapped(update, context)

        handler.assert_not_awaited()
        update.message.reply_text.assert_not_awaited()

    async def test_failed_error_reply_only_warns(self, caplog):
        """錯誤回覆本身失敗 → 只記 warning，不往外拋。"""
        update = _make_update()
        update.message.reply_text = AsyncMock(side_effect=RuntimeError("telegram down"))
        context = MagicMock()
        session = MagicMock()

        async def boom(_u, _c, _s):
            raise RuntimeError("db down")

        wrapped = _with_auth_and_session(boom, ALLOWED, _session_factory(session))

        with caplog.at_level("WARNING"):
            # Must not raise.
            await wrapped(update, context)

        assert any("Bot error reply failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
class TestHandlePaidReplyFailure:
    async def test_paid_commits_even_if_reply_fails(self, caplog):
        """handle_paid：reply 失敗仍已 commit，且不 rollback、只記 warning。"""
        update = _make_update()
        update.message.reply_text = AsyncMock(side_effect=RuntimeError("telegram down"))
        ctx = MagicMock()
        ctx.args = ["1"]
        session = AsyncMock()

        bill = MagicMock()
        bill.id = 1
        bill.is_paid = False

        with (
            patch("ccas.bot.handlers.queries") as mock_queries,
            patch("ccas.bot.handlers.formatting") as mock_fmt,
        ):
            mock_queries.fetch_bill_by_id = AsyncMock(return_value=bill)
            mock_queries.fetch_bank_names = AsyncMock(return_value={"CTBC": "中國信託"})
            mock_fmt.format_paid_success.return_value = "marked paid"

            with caplog.at_level("WARNING"):
                # Reply failure must not propagate.
                await handle_paid(update, ctx, session)

        assert bill.is_paid is True
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        assert any("/paid reply failed" in r.message for r in caplog.records)
