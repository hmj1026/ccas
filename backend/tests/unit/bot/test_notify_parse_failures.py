"""notify stage 的解析失敗通知（spec telegram-notifications：解析失敗時發送異常通知）。

以 fake transport + 真實 in-memory SQLite 驗證：多份失敗合併一則、已通知不重送、
發送失敗下次補送、無未通知帳單時仍會執行，以及失敗原因中的卡號遮罩。
"""

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.bot.job import run_notify_job
from ccas.outbox import Outbox
from ccas.storage.models import (
    BankConfig,
    Base,
    Bill,
    StagedAttachment,
    StagedAttachmentStatus,
)
from tests.unit.conftest import FakeTransport


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(BankConfig(bank_code="CTBC", bank_name="中國信託", gmail_filter="x"))
        await s.commit()
        yield s
    await engine.dispose()


async def _seed_failures(
    session: AsyncSession, n: int, *, reason: str = "找不到 parser"
) -> list[int]:
    rows = [
        StagedAttachment(
            bank_code="CTBC",
            gmail_message_id=f"m{i}",
            gmail_attachment_id="a",
            gmail_part_id="1",
            message_date=datetime(2026, 5, 1),
            original_filename=f"s{i}.pdf",
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason=reason,
        )
        for i in range(n)
    ]
    session.add_all(rows)
    await session.commit()
    return [r.id for r in rows]


async def _unnotified(session: AsyncSession) -> list[int]:
    rows = await session.execute(
        select(StagedAttachment.id).where(
            StagedAttachment.failure_notified_at.is_(None)
        )
    )
    return list(rows.scalars().all())


class TestParseFailureNotification:
    async def test_three_failures_send_exactly_one_message(self, session: AsyncSession):
        await _seed_failures(session, 3)
        transport = FakeTransport()

        summary = await run_notify_job(session, outbox=Outbox(session, transport))

        assert len(transport.sent) == 1
        text = transport.sent[0]
        assert "3 份" in text
        assert all(f"s{i}.pdf" in text for i in range(3))
        assert "中國信託" in text
        assert summary.sent_count == 1
        assert summary.failed_count == 0
        assert await _unnotified(session) == []

    async def test_already_notified_failure_is_not_resent(self, session: AsyncSession):
        await _seed_failures(session, 1)
        transport = FakeTransport()
        outbox = Outbox(session, transport)

        await run_notify_job(session, outbox=outbox)
        second = await run_notify_job(session, outbox=outbox)

        assert len(transport.sent) == 1
        assert second.sent_count == 0

    async def test_send_failure_resends_next_run(self, session: AsyncSession):
        ids = await _seed_failures(session, 2)
        transport = FakeTransport(fail_times=1)
        outbox = Outbox(session, transport)

        first = await run_notify_job(session, outbox=outbox)

        assert first.failed_count == 1
        assert sorted(await _unnotified(session)) == sorted(ids)

        second = await run_notify_job(session, outbox=outbox)

        assert second.sent_count == 1
        assert len(transport.sent) == 1
        assert await _unnotified(session) == []

    async def test_runs_when_no_unnotified_bills(self, session: AsyncSession):
        session.add(
            Bill(
                bank_code="CTBC",
                billing_month="2026-05",
                total_amount=1,
                due_date=date(2026, 6, 1),
                is_notified=True,
            )
        )
        await session.commit()
        await _seed_failures(session, 1)
        transport = FakeTransport()

        await run_notify_job(session, outbox=Outbox(session, transport))

        assert len(transport.sent) == 1

    async def test_card_number_in_reason_is_masked(self, session: AsyncSession):
        await _seed_failures(session, 1, reason="bad row 4111111111111111 here")
        transport = FakeTransport()

        await run_notify_job(session, outbox=Outbox(session, transport))

        assert "4111111111111111" not in transport.sent[0]

    async def test_parsed_attachments_are_ignored(self, session: AsyncSession):
        session.add(
            StagedAttachment(
                bank_code="CTBC",
                gmail_message_id="ok",
                gmail_attachment_id="a",
                gmail_part_id="1",
                message_date=datetime(2026, 5, 1),
                original_filename="ok.pdf",
                status=StagedAttachmentStatus.PARSED,
            )
        )
        await session.commit()
        transport = FakeTransport()

        summary = await run_notify_job(session, outbox=Outbox(session, transport))

        assert transport.sent == []
        assert summary.sent_count == 0
