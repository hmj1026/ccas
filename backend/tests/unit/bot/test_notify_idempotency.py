"""run_notify_job 通知冪等性測試。

驗證以 PaymentReminder (bill_id, "new_bill") 唯一鍵作為 send 前 claim：
1. 成功送出後重複執行不會重複發送
2. claim insert/commit 失敗時不發送
3. 發送失敗會釋放 claim，下次執行補送剛好一次
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.bot.job import NEW_BILL_REMINDER_TYPE, run_notify_job
from ccas.outbox import Outbox
from ccas.storage.models import Base, Bill, PaymentReminder


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_bill(session: AsyncSession) -> int:
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-05",
        total_amount=12345,
        due_date=date(2026, 6, 15),
    )
    session.add(bill)
    await session.commit()
    return bill.id


async def _assert_claimed_and_notified(session: AsyncSession, bill_id: int) -> None:
    """恰有一筆 claim 列，且帳單已標記 is_notified。"""
    reminders = (await session.execute(select(PaymentReminder))).scalars().all()
    assert [(r.bill_id, r.reminder_type) for r in reminders] == [
        (bill_id, NEW_BILL_REMINDER_TYPE)
    ]
    is_notified = (
        await session.execute(select(Bill.is_notified).where(Bill.id == bill_id))
    ).scalar_one()
    assert is_notified is True


class TestNotifyIdempotency:
    async def test_duplicate_run_does_not_send_twice(self, session: AsyncSession):
        """重複執行（is_notified 更新遺失）時不得重複發送。"""
        bill_id = await _seed_bill(session)
        mock_send = AsyncMock(return_value={"ok": True})

        outbox = Outbox(session, mock_send)
        first = await run_notify_job(session, outbox=outbox)

        # Simulate the worst case: send succeeded but the is_notified
        # update was lost, so the bill is re-queried on the next run.
        await session.execute(
            sa_update(Bill).where(Bill.id == bill_id).values(is_notified=False)
        )
        await session.commit()

        second = await run_notify_job(session, outbox=outbox)

        assert first.sent_count == 1
        assert second.sent_count == 0
        assert second.failed_count == 0
        assert mock_send.await_count == 1
        # The skip path repairs the flag so the bill stops being re-scanned.
        await _assert_claimed_and_notified(session, bill_id)

    async def test_claim_commit_failure_does_not_send(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        """claim insert/commit 失敗時必須跳過發送並記為失敗。"""
        await _seed_bill(session)
        mock_send = AsyncMock(return_value={"ok": True})

        async def _boom() -> None:
            raise RuntimeError("db commit failed")

        monkeypatch.setattr(session, "commit", _boom)

        outbox = Outbox(session, mock_send)
        summary = await run_notify_job(session, outbox=outbox)

        mock_send.assert_not_awaited()
        assert summary.sent_count == 0
        assert summary.failed_count == 1
        assert "db commit failed" in summary.errors[0]

    async def test_send_failure_releases_claim_for_retry(self, session: AsyncSession):
        """發送失敗必須釋放 claim，下次執行要補送剛好一次。"""
        bill_id = await _seed_bill(session)
        mock_send = AsyncMock(side_effect=[RuntimeError("telegram down"), {"ok": True}])

        outbox = Outbox(session, mock_send)
        first = await run_notify_job(session, outbox=outbox)
        second = await run_notify_job(session, outbox=outbox)

        assert first.sent_count == 0
        assert first.failed_count == 1
        assert second.sent_count == 1
        assert second.failed_count == 0
        assert mock_send.await_count == 2
        await _assert_claimed_and_notified(session, bill_id)
