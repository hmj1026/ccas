"""付款提醒整合測試。

5.6: 驗證只有 due_date 符合目標日期且未付的帳單會被選出並觸發通知。
5.7: 驗證同一帳單不會因同一提醒類型被重複通知。
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.scheduler.reminders import send_payment_reminders
from ccas.storage.models import BankConfig, Bill, PaymentReminder


async def _seed_bank(session: AsyncSession, bank_code: str = "CTBC") -> None:
    session.add(BankConfig(
        bank_code=bank_code,
        bank_name="中國信託",
        gmail_filter="from:ctbc",
    ))
    await session.flush()


async def _seed_bill(
    session: AsyncSession,
    *,
    bank_code: str = "CTBC",
    due_date: date,
    is_paid: bool = False,
) -> Bill:
    bill = Bill(
        bank_code=bank_code,
        billing_month=due_date.strftime("%Y-%m"),
        total_amount=5000,
        due_date=due_date,
        is_paid=is_paid,
    )
    session.add(bill)
    await session.flush()
    return bill


class TestPaymentReminderQuery:
    """5.6: 驗證付款提醒查詢邏輯。"""

    @pytest.mark.asyncio
    async def test_finds_bills_due_in_3_days(self, db_session: AsyncSession):
        """3 天後到期的未付帳單應被提醒。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        await _seed_bill(db_session, due_date=today + timedelta(days=3))

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 1
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_finds_bills_due_in_1_day(self, db_session: AsyncSession):
        """1 天後到期的未付帳單應被提醒。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        await _seed_bill(db_session, due_date=today + timedelta(days=1))

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 1

    @pytest.mark.asyncio
    async def test_ignores_paid_bills(self, db_session: AsyncSession):
        """已付帳單不應被提醒。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        await _seed_bill(db_session, due_date=today + timedelta(days=3), is_paid=True)

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_bills_due_in_2_days(self, db_session: AsyncSession):
        """2 天後到期的帳單不在提醒範圍（只有 3 天與 1 天）。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        await _seed_bill(db_session, due_date=today + timedelta(days=2))

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 0

    @pytest.mark.asyncio
    async def test_no_bills_runs_silently(self, db_session: AsyncSession):
        """無符合條件帳單時應靜默完成。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 0
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_both_3day_and_1day_reminders_sent(self, db_session: AsyncSession):
        """同時有 3 天與 1 天到期帳單時，兩者都應被提醒。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        await _seed_bill(db_session, due_date=today + timedelta(days=3))
        # 需要第二間銀行來避免 unique constraint
        db_session.add(BankConfig(
            bank_code="ESUN",
            bank_name="玉山銀行",
            gmail_filter="from:esun",
        ))
        await db_session.flush()
        await _seed_bill(db_session, bank_code="ESUN", due_date=today + timedelta(days=1))

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 2


class TestDuplicateReminderProtection:
    """5.7: 驗證同一帳單不會因同一提醒類型被重複通知。"""

    @pytest.mark.asyncio
    async def test_already_reminded_bill_is_skipped(self, db_session: AsyncSession):
        """已發送過 3 天提醒的帳單不再重複發送。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        bill = await _seed_bill(db_session, due_date=today + timedelta(days=3))

        # 預先插入提醒記錄
        db_session.add(PaymentReminder(bill_id=bill.id, reminder_type="3day"))
        await db_session.commit()

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        assert result["sent"] == 0
        assert result["skipped"] == 1
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_3day_reminder_does_not_block_1day(self, db_session: AsyncSession):
        """3 天提醒與 1 天提醒互相獨立。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        bill = await _seed_bill(db_session, due_date=today + timedelta(days=1))

        # 已有 3day 提醒
        db_session.add(PaymentReminder(bill_id=bill.id, reminder_type="3day"))
        await db_session.commit()

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result = await send_payment_reminders(db_session, today=today)

        # 1day 提醒仍應發送
        assert result["sent"] == 1

    @pytest.mark.asyncio
    async def test_running_twice_doesnt_duplicate(self, db_session: AsyncSession):
        """連續執行兩次，第二次應跳過已提醒的帳單。"""
        today = date(2026, 3, 31)
        await _seed_bank(db_session)
        await _seed_bill(db_session, due_date=today + timedelta(days=3))

        mock_send = AsyncMock(return_value={"ok": True})
        with patch("ccas.scheduler.reminders.send_message", mock_send):
            result1 = await send_payment_reminders(db_session, today=today)
            result2 = await send_payment_reminders(db_session, today=today)

        assert result1["sent"] == 1
        assert result2["sent"] == 0
        assert result2["skipped"] == 1
