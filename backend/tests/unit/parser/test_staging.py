"""Unit tests for ccas.parser.staging data-access helpers.

Exercises the read/write paths against a real in-memory SQLite async engine
so the SQL actually executes (cascade deletes, flush-assigned PKs, etc.).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.parser.result import ParseResult, TransactionItem
from ccas.parser.staging import (
    check_bill_exists,
    create_bill_and_transactions,
    delete_existing_bill,
    fetch_parseable_attachments,
    get_bank_config,
    update_attachment_status,
)
from ccas.shared.pipeline_types import PipelineOptions
from ccas.storage.models import (
    BankConfig,
    Base,
    Bill,
    PaymentReminder,
    StagedAttachment,
    StagedAttachmentStatus,
    Transaction,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_attachment(
    status: str,
    *,
    message_id: str = "msg-001",
    attachment_id: str = "att-001",
    staged_path: str | None = "/data/staging/CTBC/bill.pdf",
) -> StagedAttachment:
    return StagedAttachment(
        bank_code="CTBC",
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        message_date=datetime(2026, 3, 10),
        original_filename="bill.pdf",
        staged_path=staged_path,
        status=status,
    )


def _make_parse_result() -> ParseResult:
    return ParseResult(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=12345,
        due_date=date(2026, 4, 15),
        due_date_estimated=True,
        transactions=(
            TransactionItem(
                trans_date=date(2026, 3, 1),
                posting_date=date(2026, 3, 3),
                merchant="全聯福利中心",
                amount=350,
                currency="TWD",
            ),
            TransactionItem(
                trans_date=date(2026, 3, 15),
                merchant="AMAZON.COM",
                amount=403,
                currency="USD",
                original_amount=13,
                card_last4="1234",
                installment_current=2,
                installment_total=12,
            ),
        ),
    )


# -- fetch_parseable_attachments --


class TestFetchParseableAttachments:
    async def test_default_returns_decrypted_only(self, db_session):
        db_session.add(_make_attachment("decrypted", attachment_id="a1"))
        db_session.add(_make_attachment("parsed", message_id="m2", attachment_id="a2"))
        await db_session.flush()

        results = await fetch_parseable_attachments(db_session)

        assert [r.status for r in results] == ["decrypted"]

    async def test_force_widens_to_reparseable_statuses(self, db_session):
        db_session.add(_make_attachment("decrypted", attachment_id="a1"))
        db_session.add(_make_attachment("parsed", message_id="m2", attachment_id="a2"))
        db_session.add(
            _make_attachment("parse_failed", message_id="m3", attachment_id="a3")
        )
        await db_session.flush()

        results = await fetch_parseable_attachments(
            db_session, PipelineOptions(force=True)
        )

        assert {r.status for r in results} == {"decrypted", "parsed", "parse_failed"}


# -- get_bank_config --


class TestGetBankConfig:
    async def test_returns_config_when_present(self, db_session):
        db_session.add(
            BankConfig(
                bank_code="CTBC",
                bank_name="中國信託",
                gmail_filter="from:ctbc",
                active_parser_version="v1",
            )
        )
        await db_session.flush()

        config = await get_bank_config(db_session, "CTBC")

        assert config is not None
        assert config.active_parser_version == "v1"

    async def test_returns_none_when_missing(self, db_session):
        assert await get_bank_config(db_session, "UNKNOWN") is None


# -- check_bill_exists --


class TestCheckBillExists:
    async def test_true_when_bill_present(self, db_session):
        db_session.add(
            Bill(
                bank_code="CTBC",
                billing_month="2026-03",
                total_amount=100,
                due_date=date(2026, 4, 15),
            )
        )
        await db_session.flush()

        assert await check_bill_exists(db_session, "CTBC", "2026-03") is True

    async def test_false_when_absent(self, db_session):
        assert await check_bill_exists(db_session, "CTBC", "2099-01") is False


# -- delete_existing_bill --


class TestDeleteExistingBill:
    async def test_removes_bill_transactions_and_reminders(self, db_session):
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=100,
            due_date=date(2026, 4, 15),
        )
        db_session.add(bill)
        await db_session.flush()

        db_session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 3, 1),
                merchant="全聯",
                amount=350,
            )
        )
        db_session.add(PaymentReminder(bill_id=bill.id, reminder_type="due_soon"))
        await db_session.flush()

        deleted = await delete_existing_bill(db_session, "CTBC", "2026-03")

        assert deleted is True
        assert (await db_session.scalar(select(func.count()).select_from(Bill))) == 0
        assert (
            await db_session.scalar(select(func.count()).select_from(Transaction))
        ) == 0
        assert (
            await db_session.scalar(select(func.count()).select_from(PaymentReminder))
        ) == 0

    async def test_returns_false_when_bill_missing(self, db_session):
        assert await delete_existing_bill(db_session, "CTBC", "2099-12") is False


# -- create_bill_and_transactions --


class TestCreateBillAndTransactions:
    async def test_persists_bill_and_all_transactions(self, db_session):
        parse_result = _make_parse_result()

        bill = await create_bill_and_transactions(
            db_session, parse_result, file_path="/tmp/CTBC/bill.pdf"
        )

        assert bill.id is not None
        assert bill.bank_code == "CTBC"
        assert bill.billing_month == "2026-03"
        assert bill.total_amount == 12345
        assert bill.due_date == date(2026, 4, 15)
        assert bill.due_date_estimated is True
        assert bill.file_path == "/tmp/CTBC/bill.pdf"

        txns = (
            (await db_session.execute(select(Transaction).order_by(Transaction.id)))
            .scalars()
            .all()
        )
        assert len(txns) == 2
        assert all(t.bill_id == bill.id for t in txns)
        foreign = txns[1]
        assert foreign.currency == "USD"
        assert foreign.original_amount == 13
        assert foreign.card_last4 == "1234"
        assert foreign.installment_current == 2
        assert foreign.installment_total == 12

    async def test_file_path_optional(self, db_session):
        parse_result = _make_parse_result()

        bill = await create_bill_and_transactions(db_session, parse_result)

        assert bill.file_path is None


# -- update_attachment_status --


class TestUpdateAttachmentStatus:
    async def test_sets_status_and_error_reason(self, db_session):
        attachment = _make_attachment("decrypted")
        db_session.add(attachment)
        await db_session.flush()

        await update_attachment_status(
            db_session,
            attachment,
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason="boom",
        )

        assert attachment.status == StagedAttachmentStatus.PARSE_FAILED
        assert attachment.error_reason == "boom"

    async def test_clears_error_reason_on_success(self, db_session):
        attachment = _make_attachment("decrypted")
        attachment.error_reason = "previous failure"
        db_session.add(attachment)
        await db_session.flush()

        await update_attachment_status(
            db_session,
            attachment,
            status=StagedAttachmentStatus.PARSED,
        )

        assert attachment.status == StagedAttachmentStatus.PARSED
        assert attachment.error_reason is None
