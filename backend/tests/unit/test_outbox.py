"""Outbox（通知投遞）介面測試。

以 fake transport + 真實 in-memory SQLite session 驗證投遞規則：
先認領再發送、失敗釋放認領、未設定時不認領，以及各 ledger adapter 的語意。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.config import Settings
from ccas.outbox import (
    BudgetAlertsClaim,
    DeliveryStatus,
    Outbox,
    ParseFailureClaim,
    PaymentReminderClaim,
)
from ccas.storage.models import (
    Base,
    Bill,
    Budget,
    BudgetAlert,
    PaymentReminder,
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


async def _reminder_rows(session: AsyncSession) -> list[tuple[int, str]]:
    rows = (await session.execute(select(PaymentReminder))).scalars().all()
    return [(r.bill_id, r.reminder_type) for r in rows]


class TestDeliver:
    async def test_sent_keeps_claim(self, session: AsyncSession):
        bill_id = await _seed_bill(session)
        transport = FakeTransport()
        outbox = Outbox(session, transport)

        outcome = await outbox.deliver(
            PaymentReminderClaim(bill_id, "3day"), lambda: "hello"
        )

        assert outcome.status is DeliveryStatus.SENT
        assert outcome.error is None
        assert transport.sent == ["hello"]
        assert await _reminder_rows(session) == [(bill_id, "3day")]

    async def test_already_delivered_does_not_send_or_render(
        self, session: AsyncSession
    ):
        bill_id = await _seed_bill(session)
        transport = FakeTransport()
        outbox = Outbox(session, transport)
        await outbox.deliver(PaymentReminderClaim(bill_id, "3day"), lambda: "first")

        rendered: list[bool] = []

        def render() -> str:
            rendered.append(True)
            return "second"

        outcome = await outbox.deliver(PaymentReminderClaim(bill_id, "3day"), render)

        assert outcome.status is DeliveryStatus.ALREADY_DELIVERED
        assert transport.sent == ["first"]
        assert rendered == []

    async def test_failed_send_releases_claim_then_retry_sends_once(
        self, session: AsyncSession
    ):
        bill_id = await _seed_bill(session)
        transport = FakeTransport(fail_times=1)
        outbox = Outbox(session, transport)

        first = await outbox.deliver(PaymentReminderClaim(bill_id, "1day"), lambda: "x")

        assert first.status is DeliveryStatus.FAILED
        assert isinstance(first.error, RuntimeError)
        assert await _reminder_rows(session) == []

        second = await outbox.deliver(
            PaymentReminderClaim(bill_id, "1day"), lambda: "x"
        )

        assert second.status is DeliveryStatus.SENT
        assert transport.sent == ["x"]
        assert await _reminder_rows(session) == [(bill_id, "1day")]

    async def test_render_failure_releases_claim(self, session: AsyncSession):
        bill_id = await _seed_bill(session)
        outbox = Outbox(session, FakeTransport())

        def render() -> str:
            raise ValueError("bad template")

        outcome = await outbox.deliver(PaymentReminderClaim(bill_id, "3day"), render)

        assert outcome.status is DeliveryStatus.FAILED
        assert await _reminder_rows(session) == []

    async def test_release_failure_is_logged_and_outcome_still_failed(
        self, session: AsyncSession, caplog: pytest.LogCaptureFixture
    ):
        bill_id = await _seed_bill(session)
        outbox = Outbox(session, FakeTransport(fail_times=1))

        class BrokenRelease(PaymentReminderClaim):
            async def release(self, session: AsyncSession) -> None:
                raise RuntimeError("db gone")

        with caplog.at_level(logging.ERROR, logger="ccas.outbox"):
            outcome = await outbox.deliver(BrokenRelease(bill_id, "3day"), lambda: "x")

        assert outcome.status is DeliveryStatus.FAILED
        assert "telegram down" in str(outcome.error)
        assert any("釋放" in r.getMessage() for r in caplog.records)
        # 釋放失敗 → claim 留存，需人工確認。
        assert await _reminder_rows(session) == [(bill_id, "3day")]

    async def test_acquire_failure_is_failed_without_send(self, session: AsyncSession):
        bill_id = await _seed_bill(session)
        transport = FakeTransport()

        class BrokenAcquire(PaymentReminderClaim):
            async def acquire(self, session: AsyncSession) -> bool:
                raise RuntimeError("db commit failed")

        outcome = await Outbox(session, transport).deliver(
            BrokenAcquire(bill_id, "3day"), lambda: "x"
        )

        assert outcome.status is DeliveryStatus.FAILED
        assert "db commit failed" in str(outcome.error)
        assert transport.sent == []

    async def test_unconfigured_skips_without_claim(self, session: AsyncSession):
        bill_id = await _seed_bill(session)
        outbox = Outbox(session, None)

        outcome = await outbox.deliver(
            PaymentReminderClaim(bill_id, "3day"), lambda: "x"
        )

        assert outcome.status is DeliveryStatus.SKIPPED_UNCONFIGURED
        assert not outbox.configured
        assert await _reminder_rows(session) == []


class TestFromSettings:
    def _settings(self, token: str, chat_id: str) -> Settings:
        settings = Settings()
        settings.telegram_bot_token = SecretStr(token)
        settings.telegram_chat_id = chat_id
        return settings

    @pytest.mark.parametrize(("token", "chat_id"), [("", "1"), ("t", ""), ("", "")])
    async def test_missing_token_or_chat_is_unconfigured(
        self, session: AsyncSession, token: str, chat_id: str
    ):
        outbox = Outbox.from_settings(self._settings(token, chat_id), session)
        assert not outbox.configured

    async def test_configured_uses_injected_transport(self, session: AsyncSession):
        transport = FakeTransport()
        outbox = Outbox.from_settings(
            self._settings("t", "1"), session, transport=transport
        )
        bill_id = await _seed_bill(session)

        await outbox.deliver(PaymentReminderClaim(bill_id, "3day"), lambda: "hi")

        assert outbox.configured
        assert transport.sent == ["hi"]


class TestBudgetAlertsClaim:
    async def _seed_alerts(
        self, session: AsyncSession, *, notified: bool
    ) -> list[BudgetAlert]:
        budget = Budget(
            scope="monthly_total",
            scope_ref=None,
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
        session.add(budget)
        await session.flush()
        alerts = [
            BudgetAlert(
                budget_id=budget.id,
                period_year_month="2026-05",
                threshold_breached_percent=tier,
                current_amount_ntd=11000,
                triggered_at=datetime.now(UTC),
                notified=notified,
            )
            for tier in (80, 100)
        ]
        session.add_all(alerts)
        await session.commit()
        return alerts

    async def test_sent_marks_all_alerts_notified(self, session: AsyncSession):
        alerts = await self._seed_alerts(session, notified=False)
        transport = FakeTransport()

        outcome = await Outbox(session, transport).deliver(
            BudgetAlertsClaim(alerts), lambda: "budget"
        )

        assert outcome.status is DeliveryStatus.SENT
        assert transport.sent == ["budget"]
        notified = (await session.execute(select(BudgetAlert.notified))).scalars()
        assert list(notified) == [True, True]

    async def test_failed_send_leaves_alerts_pending(self, session: AsyncSession):
        alerts = await self._seed_alerts(session, notified=False)

        outcome = await Outbox(session, FakeTransport(fail_times=1)).deliver(
            BudgetAlertsClaim(alerts), lambda: "budget"
        )

        assert outcome.status is DeliveryStatus.FAILED
        notified = (await session.execute(select(BudgetAlert.notified))).scalars()
        assert list(notified) == [False, False]

    async def test_all_notified_is_already_delivered(self, session: AsyncSession):
        alerts = await self._seed_alerts(session, notified=True)
        transport = FakeTransport()

        outcome = await Outbox(session, transport).deliver(
            BudgetAlertsClaim(alerts), lambda: "budget"
        )

        assert outcome.status is DeliveryStatus.ALREADY_DELIVERED
        assert transport.sent == []


class TestParseFailureClaim:
    async def _seed_failures(self, session: AsyncSession, n: int) -> list[int]:
        rows = [
            StagedAttachment(
                bank_code="CTBC",
                gmail_message_id=f"m{i}",
                gmail_attachment_id="a",
                gmail_part_id="1",
                message_date=datetime(2026, 5, 1),
                original_filename=f"s{i}.pdf",
                status=StagedAttachmentStatus.PARSE_FAILED,
                error_reason="no parser",
            )
            for i in range(n)
        ]
        session.add_all(rows)
        await session.commit()
        return [r.id for r in rows]

    async def _notified(self, session: AsyncSession) -> dict[int, bool]:
        rows = await session.execute(
            select(StagedAttachment.id, StagedAttachment.failure_notified_at)
        )
        return {i: ts is not None for i, ts in rows.all()}

    async def test_claims_only_unnotified_and_exposes_claimed_ids(
        self, session: AsyncSession
    ):
        ids = await self._seed_failures(session, 3)
        first = ParseFailureClaim([ids[0]])
        await Outbox(session, FakeTransport()).deliver(first, lambda: "one")

        claim = ParseFailureClaim(ids)
        transport = FakeTransport()
        outcome = await Outbox(session, transport).deliver(
            claim, lambda: ",".join(map(str, claim.claimed_ids))
        )

        assert outcome.status is DeliveryStatus.SENT
        assert claim.claimed_ids == ids[1:]
        assert transport.sent == [f"{ids[1]},{ids[2]}"]
        assert await self._notified(session) == dict.fromkeys(ids, True)

    async def test_failed_send_releases_only_claimed(self, session: AsyncSession):
        ids = await self._seed_failures(session, 2)
        await Outbox(session, FakeTransport()).deliver(
            ParseFailureClaim([ids[0]]), lambda: "one"
        )

        outcome = await Outbox(session, FakeTransport(fail_times=1)).deliver(
            ParseFailureClaim(ids), lambda: "both"
        )

        assert outcome.status is DeliveryStatus.FAILED
        assert await self._notified(session) == {ids[0]: True, ids[1]: False}

    async def test_nothing_to_claim_is_already_delivered(self, session: AsyncSession):
        transport = FakeTransport()
        outcome = await Outbox(session, transport).deliver(
            ParseFailureClaim([]), lambda: "x"
        )
        assert outcome.status is DeliveryStatus.ALREADY_DELIVERED
        assert transport.sent == []
