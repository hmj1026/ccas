"""UBOT parse job integration tests.

Successful parse writes Bill + Transaction, attachment status updated.
"""

import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.parser.base import BankParser
from ccas.parser.job import run_parse_job
from ccas.parser.registry import _ParserRegistry
from ccas.parser.result import ParseResult, TransactionItem
from ccas.storage.models import (
    BankConfig,
    Base,
    Bill,
    StagedAttachment,
    Transaction,
)

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("API_TOKEN", "test")


class FakeUbotParser(BankParser):
    """Fake UBOT parser that always succeeds."""

    bank_code = "UBOT"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        return ParseResult(
            bank_code="UBOT",
            billing_month="2026-03",
            total_amount=6530,
            due_date=date(2026, 4, 18),
            transactions=(
                TransactionItem(
                    trans_date=date(2026, 3, 5),
                    merchant="7-ELEVEN",
                    amount=120,
                    posting_date=date(2026, 3, 7),
                    card_last4="3456",
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 12),
                    merchant="全聯福利中心",
                    amount=1850,
                    posting_date=date(2026, 3, 14),
                    card_last4="3456",
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 20),
                    merchant="PChome線上購物",
                    amount=3200,
                ),
            ),
        )


async def _create_test_session():
    """Create in-memory DB + session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


class TestUbotParseJob:
    """UBOT parse job integration tests."""

    async def test_parse_creates_bill_and_transactions(self) -> None:
        """Parse job creates Bill and Transaction records for UBOT."""
        test_registry = _ParserRegistry()
        test_registry.register(FakeUbotParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="UBOT",
                    bank_name="聯邦銀行",
                    gmail_filter="from:ubot",
                    active_parser_version="v1",
                )
            )
            session.add(
                StagedAttachment(
                    bank_code="UBOT",
                    gmail_message_id="msg-ubot-1",
                    gmail_attachment_id="att-ubot-1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="ubot-bill.pdf",
                    staged_path="/tmp/ubot.pdf",
                    status="decrypted",
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            assert summary.parsed_count == 1
            assert summary.failed_count == 0
            assert summary.skipped_count == 0

            # Verify Bill record
            bills = (await session.execute(select(Bill))).scalars().all()
            assert len(bills) == 1
            assert bills[0].bank_code == "UBOT"
            assert bills[0].billing_month == "2026-03"
            assert bills[0].total_amount == 6530
            assert bills[0].due_date == date(2026, 4, 18)

            # Verify Transaction records
            txns = (await session.execute(select(Transaction))).scalars().all()
            assert len(txns) == 3
            merchants = {t.merchant for t in txns}
            assert merchants == {"7-ELEVEN", "全聯福利中心", "PChome線上購物"}
            amounts = {t.amount for t in txns}
            assert amounts == {120, 1850, 3200}

        await engine.dispose()

    async def test_attachment_status_updated_to_parsed(self) -> None:
        """Parse job updates attachment status to 'parsed'."""
        test_registry = _ParserRegistry()
        test_registry.register(FakeUbotParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="UBOT",
                    bank_name="聯邦銀行",
                    gmail_filter="from:ubot",
                    active_parser_version="v1",
                )
            )
            session.add(
                StagedAttachment(
                    bank_code="UBOT",
                    gmail_message_id="msg-ubot-1",
                    gmail_attachment_id="att-ubot-1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="ubot-bill.pdf",
                    staged_path="/tmp/ubot.pdf",
                    status="decrypted",
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                await run_parse_job(session)

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-ubot-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parsed"
            assert att.error_reason is None

        await engine.dispose()
