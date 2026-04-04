"""Telegram Bot handler 單元測試。

驗證 5 個指令 handler 的邏輯分支：
- 參數驗證（無效/缺少參數）
- 正常查詢路徑
- 邊界條件（bill 不存在、已繳）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.bot.handlers import (
    handle_category,
    handle_paid,
    handle_status,
    handle_summary,
    handle_upcoming,
)


def _make_update() -> MagicMock:
    """建立 mock Update，含 message.reply_text AsyncMock。"""
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _make_context(args: list[str] | None = None) -> MagicMock:
    """建立 mock Context，含指定 args。"""
    ctx = MagicMock()
    ctx.args = args
    return ctx


def _make_bill(
    *,
    bill_id: int = 1,
    bank_code: str = "CTBC",
    is_paid: bool = False,
) -> MagicMock:
    bill = MagicMock()
    bill.id = bill_id
    bill.bank_code = bank_code
    bill.is_paid = is_paid
    return bill


BANK_NAMES = {"CTBC": "中國信託"}


# -- handle_status --


@pytest.mark.asyncio
class TestHandleStatus:
    """驗證 /status 指令。"""

    async def test_invalid_filter_replies_error(self):
        update = _make_update()
        ctx = _make_context(["invalid"])
        session = AsyncMock()

        await handle_status(update, ctx, session)

        reply = update.message.reply_text
        reply.assert_awaited_once()
        assert "無效的篩選條件" in reply.call_args[0][0]

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_default_filter_is_all(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(None)
        session = AsyncMock()
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_queries.fetch_bills_by_month = AsyncMock(return_value=[])
        mock_fmt.format_status.return_value = "status text"

        await handle_status(update, ctx, session)

        mock_queries.fetch_bills_by_month.assert_awaited_once()
        call_kwargs = mock_queries.fetch_bills_by_month.call_args
        assert call_kwargs[1]["paid_filter"] == "all"
        update.message.reply_text.assert_awaited_once_with("status text")

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_paid_filter(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(["paid"])
        session = AsyncMock()
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_queries.fetch_bills_by_month = AsyncMock(return_value=[])
        mock_fmt.format_status.return_value = "paid text"

        await handle_status(update, ctx, session)

        call_kwargs = mock_queries.fetch_bills_by_month.call_args
        assert call_kwargs[1]["paid_filter"] == "paid"

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_unpaid_filter(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(["unpaid"])
        session = AsyncMock()
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_queries.fetch_bills_by_month = AsyncMock(return_value=[])
        mock_fmt.format_status.return_value = "unpaid text"

        await handle_status(update, ctx, session)

        call_kwargs = mock_queries.fetch_bills_by_month.call_args
        assert call_kwargs[1]["paid_filter"] == "unpaid"


# -- handle_upcoming --


@pytest.mark.asyncio
class TestHandleUpcoming:
    """驗證 /upcoming 指令。"""

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_replies_with_formatted_text(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context()
        session = AsyncMock()
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_queries.fetch_upcoming_bills = AsyncMock(return_value=[])
        mock_fmt.format_upcoming.return_value = "upcoming text"

        await handle_upcoming(update, ctx, session)

        mock_queries.fetch_upcoming_bills.assert_awaited_once_with(session)
        update.message.reply_text.assert_awaited_once_with("upcoming text")


# -- handle_summary --


@pytest.mark.asyncio
class TestHandleSummary:
    """驗證 /summary 指令。"""

    async def test_no_args_replies_usage(self):
        update = _make_update()
        ctx = _make_context([])
        session = AsyncMock()

        await handle_summary(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "用法" in reply_text

    async def test_invalid_month_replies_error(self):
        update = _make_update()
        ctx = _make_context(["2026-13"])
        session = AsyncMock()

        await handle_summary(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "無效的月份格式" in reply_text

    async def test_non_date_string_replies_error(self):
        update = _make_update()
        ctx = _make_context(["abc"])
        session = AsyncMock()

        await handle_summary(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "無效的月份格式" in reply_text

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_valid_month_queries_and_formats(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(["2026-03"])
        session = AsyncMock()
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_queries.fetch_bills_by_month = AsyncMock(return_value=[])
        mock_fmt.format_summary.return_value = "summary text"

        await handle_summary(update, ctx, session)

        mock_queries.fetch_bills_by_month.assert_awaited_once_with(session, "2026-03")
        update.message.reply_text.assert_awaited_once_with("summary text")


# -- handle_category --


@pytest.mark.asyncio
class TestHandleCategory:
    """驗證 /category 指令。"""

    async def test_no_args_replies_usage(self):
        update = _make_update()
        ctx = _make_context([])
        session = AsyncMock()

        await handle_category(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "用法" in reply_text

    async def test_invalid_month_replies_error(self):
        update = _make_update()
        ctx = _make_context(["2026-00"])
        session = AsyncMock()

        await handle_category(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "無效的月份格式" in reply_text

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_valid_month_queries_and_formats(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(["2026-03"])
        session = AsyncMock()
        mock_queries.fetch_category_summary = AsyncMock(return_value=[])
        mock_fmt.format_category_summary.return_value = "category text"

        await handle_category(update, ctx, session)

        mock_queries.fetch_category_summary.assert_awaited_once_with(session, "2026-03")
        update.message.reply_text.assert_awaited_once_with("category text")


# -- handle_paid --


@pytest.mark.asyncio
class TestHandlePaid:
    """驗證 /paid 指令。"""

    async def test_no_args_replies_usage(self):
        update = _make_update()
        ctx = _make_context([])
        session = AsyncMock()

        await handle_paid(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "用法" in reply_text

    async def test_non_numeric_id_replies_error(self):
        update = _make_update()
        ctx = _make_context(["abc"])
        session = AsyncMock()

        await handle_paid(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "無效的帳單編號" in reply_text

    @patch("ccas.bot.handlers.queries")
    async def test_bill_not_found_replies_error(self, mock_queries):
        update = _make_update()
        ctx = _make_context(["999"])
        session = AsyncMock()
        mock_queries.fetch_bill_by_id = AsyncMock(return_value=None)

        await handle_paid(update, ctx, session)

        reply_text = update.message.reply_text.call_args[0][0]
        assert "找不到帳單" in reply_text

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_already_paid_replies_already(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(["1"])
        session = AsyncMock()
        bill = _make_bill(is_paid=True)
        mock_queries.fetch_bill_by_id = AsyncMock(return_value=bill)
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_fmt.format_paid_already.return_value = "already paid"

        await handle_paid(update, ctx, session)

        mock_fmt.format_paid_already.assert_called_once_with(bill, BANK_NAMES)
        session.commit.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with("already paid")

    @patch("ccas.bot.handlers.formatting")
    @patch("ccas.bot.handlers.queries")
    async def test_mark_paid_success(self, mock_queries, mock_fmt):
        update = _make_update()
        ctx = _make_context(["1"])
        session = AsyncMock()
        bill = _make_bill(is_paid=False)
        mock_queries.fetch_bill_by_id = AsyncMock(return_value=bill)
        mock_queries.fetch_bank_names = AsyncMock(return_value=BANK_NAMES)
        mock_fmt.format_paid_success.return_value = "marked paid"

        await handle_paid(update, ctx, session)

        assert bill.is_paid is True
        session.commit.assert_awaited_once()
        mock_fmt.format_paid_success.assert_called_once_with(bill, BANK_NAMES)
        update.message.reply_text.assert_awaited_once_with("marked paid")
