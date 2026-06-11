"""Payment reminder settings API（bills-management-and-insights §5）。

CRUD for ``reminder_settings`` 表 + 即時測試推送：

- ``GET /api/reminders/settings``：列出所有未付帳單與其設定（無 row → 預設值）
- ``PUT /api/reminders/{bill_id}/settings``：partial update；upsert 一筆 row
- ``POST /api/reminders/{bill_id}/test``：依 channel 立即推送一次測試訊息

Settings row 缺席時採預設行為 ``enabled=true / days_before=[3,1] /
channel=telegram``，與 change 前 ``send_payment_reminders`` 邏輯等價。
"""

from __future__ import annotations

import logging
from typing import cast, get_args

from fastapi import APIRouter, Depends, HTTPException
from pydantic import field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    ReminderChannelLiteral,
    ReminderSettingItem,
    ReminderSettingUpdateRequest,
    ReminderTestResult,
)
from ccas.config import get_settings
from ccas.messaging import render_due_reminder, send_message
from ccas.storage.database import get_db_session
from ccas.storage.models import (
    Bill,
    ReminderChannel,
    ReminderSetting,
)
from ccas.storage.queries import fetch_bank_names

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

DEFAULT_DAYS_BEFORE: list[int] = [3, 1]
DEFAULT_CHANNEL: ReminderChannelLiteral = "telegram"


# Add validator at request schema level via subclass — keep API import minimal.
class _ValidatedUpdate(ReminderSettingUpdateRequest):
    @field_validator("days_before")
    @classmethod
    def _validate_days(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not all(isinstance(d, int) and d >= 1 for d in v):
            raise ValueError("days_before 元素必須為正整數")
        return v


def _channel_str(channel: ReminderChannel | str) -> ReminderChannelLiteral:
    """Normalise enum / DB string back to API literal; fail fast on unknown."""
    val = channel.value if isinstance(channel, ReminderChannel) else str(channel)
    if val not in get_args(ReminderChannelLiteral):
        # HTTPException (not ValueError): an unknown DB value must surface as
        # a clean 500 through FastAPI, not an unhandled exception traceback.
        raise HTTPException(
            status_code=500, detail=f"DB contains unknown reminder channel: {val!r}"
        )
    return cast(ReminderChannelLiteral, val)


@router.get("/settings", response_model=ApiResponse[list[ReminderSettingItem]])
async def list_reminder_settings(
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ReminderSettingItem]]:
    """列出所有未付帳單與其提醒設定（無 row 時回預設值）。"""
    bank_names = await fetch_bank_names(session)

    bills_stmt = (
        select(Bill)
        .where(Bill.is_paid.is_(False))
        .order_by(Bill.due_date.asc(), Bill.bank_code)
    )
    bills = (await session.execute(bills_stmt)).scalars().all()

    settings_stmt = select(ReminderSetting)
    settings_rows = (await session.execute(settings_stmt)).scalars().all()
    by_bill_id = {row.bill_id: row for row in settings_rows}

    items: list[ReminderSettingItem] = []
    for bill in bills:
        setting = by_bill_id.get(bill.id)
        if setting is not None:
            items.append(
                ReminderSettingItem(
                    bill_id=bill.id,
                    bank_code=bill.bank_code,
                    bank_name=bank_names.get(bill.bank_code),
                    billing_month=bill.billing_month,
                    due_date=bill.due_date,
                    is_paid=bill.is_paid,
                    enabled=setting.enabled,
                    days_before=list(setting.days_before),
                    channel=_channel_str(setting.channel),
                    has_setting=True,
                )
            )
        else:
            items.append(
                ReminderSettingItem(
                    bill_id=bill.id,
                    bank_code=bill.bank_code,
                    bank_name=bank_names.get(bill.bank_code),
                    billing_month=bill.billing_month,
                    due_date=bill.due_date,
                    is_paid=bill.is_paid,
                    enabled=True,
                    days_before=list(DEFAULT_DAYS_BEFORE),
                    channel=DEFAULT_CHANNEL,
                    has_setting=False,
                )
            )

    return ApiResponse(data=items)


async def _get_bill_or_404(session: AsyncSession, bill_id: int) -> Bill:
    bill = await session.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail=f"找不到帳單 #{bill_id}")
    return bill


@router.put(
    "/{bill_id}/settings",
    response_model=ApiResponse[ReminderSettingItem],
)
async def update_reminder_setting(
    bill_id: int,
    body: _ValidatedUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ReminderSettingItem]:
    """Upsert reminder setting for the given bill。"""
    bill = await _get_bill_or_404(session, bill_id)

    setting = await session.get(ReminderSetting, bill_id)
    if setting is None:
        setting = ReminderSetting(
            bill_id=bill_id,
            enabled=body.enabled if body.enabled is not None else True,
            days_before=body.days_before
            if body.days_before is not None
            else list(DEFAULT_DAYS_BEFORE),
            channel=ReminderChannel(body.channel)
            if body.channel is not None
            else ReminderChannel.TELEGRAM,
        )
        session.add(setting)
    else:
        if body.enabled is not None:
            setting.enabled = body.enabled
        if body.days_before is not None:
            setting.days_before = body.days_before
        if body.channel is not None:
            setting.channel = ReminderChannel(body.channel)

    await session.commit()
    await session.refresh(setting)

    bank_names = await fetch_bank_names(session)
    return ApiResponse(
        data=ReminderSettingItem(
            bill_id=bill.id,
            bank_code=bill.bank_code,
            bank_name=bank_names.get(bill.bank_code),
            billing_month=bill.billing_month,
            due_date=bill.due_date,
            is_paid=bill.is_paid,
            enabled=setting.enabled,
            days_before=list(setting.days_before),
            channel=_channel_str(setting.channel),
            has_setting=True,
        )
    )


@router.post(
    "/{bill_id}/test",
    response_model=ApiResponse[ReminderTestResult],
)
async def push_reminder_test(
    bill_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ReminderTestResult]:
    """立即推送一次測試提醒訊息。

    ``ui_banner`` channel 不外送（前端 banner 由 unpaid bill 列表展示），
    回 ``sent=false`` + detail 提示。``telegram`` / ``both`` 走 Telegram；
    settings 不存在時走 telegram 預設。
    """
    bill = await _get_bill_or_404(session, bill_id)
    setting = await session.get(ReminderSetting, bill_id)
    channel: ReminderChannelLiteral = (
        _channel_str(setting.channel) if setting is not None else DEFAULT_CHANNEL
    )

    if channel == "ui_banner":
        return ApiResponse(
            data=ReminderTestResult(
                sent=False,
                channel=channel,
                detail="ui_banner 不外送，無需測試推播",
            )
        )

    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return ApiResponse(
            data=ReminderTestResult(
                sent=False,
                channel=channel,
                detail="TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定",
            )
        )

    bank_names = await fetch_bank_names(session)
    bank_name = bank_names.get(bill.bank_code, bill.bank_code)
    text = "[測試] " + render_due_reminder(bill, bank_name, days_until_due=3)
    try:
        await send_message(settings.telegram_bot_token, settings.telegram_chat_id, text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Test reminder push failed: %s", exc)
        return ApiResponse(
            data=ReminderTestResult(
                sent=False, channel=channel, detail=f"推播失敗：{exc}"
            )
        )

    return ApiResponse(
        data=ReminderTestResult(
            sent=True, channel=channel, detail="已送出 Telegram 測試訊息"
        )
    )
