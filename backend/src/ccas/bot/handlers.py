"""Telegram Bot 指令 handler。

每個 handler 接收 Update 與 Context，透過 queries 取得資料、
formatting 產生回覆文字，再送出訊息。
"""

import logging
import re
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from ccas.bot import formatting, queries

logger = logging.getLogger(__name__)

_MONTH_PATTERN = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_FILTER_VALUES = {"all", "unpaid", "paid"}
_FILTER_LABELS = {"all": "全部", "unpaid": "未繳", "paid": "已繳"}


async def handle_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AsyncSession,
) -> None:
    """處理 /status [all|unpaid|paid] 指令。"""
    args = context.args or []
    filter_value = args[0].lower() if args else "all"

    if filter_value not in _FILTER_VALUES:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"無效的篩選條件：{filter_value}\n"
            "用法：/status [all|unpaid|paid]"
        )
        return

    today = date.today()
    billing_month = today.strftime("%Y-%m")
    bank_names = await queries.fetch_bank_names(session)
    bills = await queries.fetch_bills_by_month(
        session, billing_month, paid_filter=filter_value
    )
    text = formatting.format_status(
        bills, bank_names, filter_label=_FILTER_LABELS[filter_value]
    )
    await update.message.reply_text(text)  # type: ignore[union-attr]


async def handle_upcoming(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AsyncSession,
) -> None:
    """處理 /upcoming 指令。"""
    bank_names = await queries.fetch_bank_names(session)
    bills = await queries.fetch_upcoming_bills(session)
    text = formatting.format_upcoming(bills, bank_names)
    await update.message.reply_text(text)  # type: ignore[union-attr]


async def handle_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AsyncSession,
) -> None:
    """處理 /summary {YYYY-MM} 指令。"""
    args = context.args or []
    if not args:
        await update.message.reply_text(  # type: ignore[union-attr]
            "請提供月份。用法：/summary 2026-03"
        )
        return

    billing_month = args[0]
    if not _MONTH_PATTERN.match(billing_month):
        await update.message.reply_text(  # type: ignore[union-attr]
            f"無效的月份格式：{billing_month}\n"
            "用法：/summary YYYY-MM"
        )
        return

    bank_names = await queries.fetch_bank_names(session)
    bills = await queries.fetch_bills_by_month(session, billing_month)
    text = formatting.format_summary(bills, bank_names, billing_month)
    await update.message.reply_text(text)  # type: ignore[union-attr]


async def handle_category(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AsyncSession,
) -> None:
    """處理 /category {YYYY-MM} 指令。"""
    args = context.args or []
    if not args:
        await update.message.reply_text(  # type: ignore[union-attr]
            "請提供月份。用法：/category 2026-03"
        )
        return

    billing_month = args[0]
    if not _MONTH_PATTERN.match(billing_month):
        await update.message.reply_text(  # type: ignore[union-attr]
            f"無效的月份格式：{billing_month}\n"
            "用法：/category YYYY-MM"
        )
        return

    rows = await queries.fetch_category_summary(session, billing_month)
    text = formatting.format_category_summary(rows, billing_month)
    await update.message.reply_text(text)  # type: ignore[union-attr]


async def handle_paid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AsyncSession,
) -> None:
    """處理 /paid {bill_id} 指令。"""
    args = context.args or []
    if not args:
        await update.message.reply_text(  # type: ignore[union-attr]
            "請提供帳單編號。用法：/paid 123"
        )
        return

    raw_id = args[0]
    if not raw_id.isdigit():
        await update.message.reply_text(  # type: ignore[union-attr]
            f"無效的帳單編號：{raw_id}\n"
            "帳單編號須為數字。"
        )
        return

    bill_id = int(raw_id)
    bill = await queries.fetch_bill_by_id(session, bill_id)

    if bill is None:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"找不到帳單 #{bill_id}。\n"
            "請確認帳單編號是否正確。"
        )
        return

    bank_names = await queries.fetch_bank_names(session)

    if bill.is_paid:
        text = formatting.format_paid_already(bill, bank_names)
    else:
        bill.is_paid = True
        await session.commit()
        text = formatting.format_paid_success(bill, bank_names)

    await update.message.reply_text(text)  # type: ignore[union-attr]
