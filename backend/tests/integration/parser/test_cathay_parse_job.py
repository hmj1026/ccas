"""CATHAY parse job integration test: parse writes Bill + Transaction."""

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
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")
os.environ.setdefault("API_TOKEN", "test")


class FakeCathayParser(BankParser):
    """Fake CATHAY parser that always succeeds."""

    bank_code = "CATHAY"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        return ParseResult(
            bank_code="CATHAY",
            billing_month="2026-03",
            total_amount=9200,
            due_date=date(2026, 4, 12),
            transactions=(
                TransactionItem(
                    trans_date=date(2026, 3, 2),
                    merchant="全家便利商店",
                    amount=180,
                    posting_date=date(2026, 3, 4),
                    card_last4="2345",
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 10),
                    merchant="誠品書店",
                    amount=1450,
                    posting_date=date(2026, 3, 12),
                    card_last4="2345",
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 18),
                    merchant="好市多",
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


class TestCathayParseJob:
    """CATHAY parse job integration tests."""

    async def test_parse_creates_bill_and_transactions(self) -> None:
        """Parse job creates Bill and Transaction records for CATHAY."""
        test_registry = _ParserRegistry()
        test_registry.register(FakeCathayParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="CATHAY",
                    bank_name="國泰世華銀行",
                    gmail_filter="from:cathay",
                    active_parser_version="v1",
                )
            )
            session.add(
                StagedAttachment(
                    bank_code="CATHAY",
                    gmail_message_id="msg-cathay-1",
                    gmail_attachment_id="att-cathay-1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="cathay-bill.pdf",
                    staged_path="/tmp/cathay.pdf",
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
            assert bills[0].bank_code == "CATHAY"
            assert bills[0].billing_month == "2026-03"
            assert bills[0].total_amount == 9200
            assert bills[0].due_date == date(2026, 4, 12)

            # Verify Transaction records
            txns = (await session.execute(select(Transaction))).scalars().all()
            assert len(txns) == 3
            merchants = {t.merchant for t in txns}
            assert merchants == {"全家便利商店", "誠品書店", "好市多"}
            amounts = {t.amount for t in txns}
            assert amounts == {180, 1450, 3200}

        await engine.dispose()

    async def test_attachment_status_updated_to_parsed(self) -> None:
        """Parse job updates attachment status to 'parsed'."""
        test_registry = _ParserRegistry()
        test_registry.register(FakeCathayParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="CATHAY",
                    bank_name="國泰世華銀行",
                    gmail_filter="from:cathay",
                    active_parser_version="v1",
                )
            )
            session.add(
                StagedAttachment(
                    bank_code="CATHAY",
                    gmail_message_id="msg-cathay-1",
                    gmail_attachment_id="att-cathay-1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="cathay-bill.pdf",
                    staged_path="/tmp/cathay.pdf",
                    status="decrypted",
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                await run_parse_job(session)

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-cathay-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parsed"
            assert att.error_reason is None

        await engine.dispose()
