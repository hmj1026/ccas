"""ESUN parse job 整合測試：成功解析寫入 Bill + Transaction，附件狀態更新。"""

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


class FakeEsunParser(BankParser):
    """Fake ESUN parser that always succeeds."""

    bank_code = "ESUN"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        return ParseResult(
            bank_code="ESUN",
            billing_month="2026-03",
            total_amount=1880,
            due_date=date(2026, 4, 15),
            transactions=(
                TransactionItem(
                    trans_date=date(2026, 3, 1),
                    merchant="全家便利商店",
                    amount=350,
                    posting_date=date(2026, 3, 3),
                    card_last4="4567",
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 8),
                    merchant="蝦皮購物",
                    amount=1280,
                    posting_date=date(2026, 3, 10),
                    card_last4="4567",
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 15),
                    merchant="星巴克",
                    amount=250,
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


class TestEsunParseJob:
    """ESUN parse job integration tests."""

    async def test_parse_creates_bill_and_transactions(self) -> None:
        """Parse job creates Bill and Transaction records for ESUN."""
        test_registry = _ParserRegistry()
        test_registry.register(FakeEsunParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="ESUN",
                    bank_name="玉山銀行",
                    gmail_filter="from:esun",
                    active_parser_version="v1",
                )
            )
            session.add(
                StagedAttachment(
                    bank_code="ESUN",
                    gmail_message_id="msg-esun-1",
                    gmail_attachment_id="att-esun-1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="esun-bill.pdf",
                    staged_path="/tmp/esun.pdf",
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
            assert bills[0].bank_code == "ESUN"
            assert bills[0].billing_month == "2026-03"
            assert bills[0].total_amount == 1880
            assert bills[0].due_date == date(2026, 4, 15)

            # Verify Transaction records
            txns = (await session.execute(select(Transaction))).scalars().all()
            assert len(txns) == 3
            merchants = {t.merchant for t in txns}
            assert merchants == {"全家便利商店", "蝦皮購物", "星巴克"}
            amounts = {t.amount for t in txns}
            assert amounts == {350, 1280, 250}

        await engine.dispose()

    async def test_attachment_status_updated_to_parsed(self) -> None:
        """Parse job updates attachment status to 'parsed'."""
        test_registry = _ParserRegistry()
        test_registry.register(FakeEsunParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(
                BankConfig(
                    bank_code="ESUN",
                    bank_name="玉山銀行",
                    gmail_filter="from:esun",
                    active_parser_version="v1",
                )
            )
            session.add(
                StagedAttachment(
                    bank_code="ESUN",
                    gmail_message_id="msg-esun-1",
                    gmail_attachment_id="att-esun-1",
                    message_date=datetime(2026, 3, 10),
                    original_filename="esun-bill.pdf",
                    staged_path="/tmp/esun.pdf",
                    status="decrypted",
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                await run_parse_job(session)

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-esun-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parsed"
            assert att.error_reason is None

        await engine.dispose()
