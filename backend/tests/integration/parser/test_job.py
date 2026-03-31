"""批次解析 job 的整合測試：成功解析、失敗標記、去重複保護。"""

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

from ccas.parser.base import BankParser, ParseError
from ccas.parser.job import run_parse_job
from ccas.parser.registry import _ParserRegistry
from ccas.parser.result import ParseResult, TransactionItem
from ccas.storage.models import (
    Base,
    BankConfig,
    Bill,
    StagedAttachment,
    Transaction,
)

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")
os.environ.setdefault("API_TOKEN", "test")


class FakeSuccessParser(BankParser):
    """永遠成功解析的假 parser。"""

    bank_code = "CTBC"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        return ParseResult(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=date(2026, 4, 15),
            transactions=(
                TransactionItem(
                    trans_date=date(2026, 3, 1),
                    merchant="星巴克",
                    amount=150,
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 5),
                    posting_date=date(2026, 3, 7),
                    merchant="全聯",
                    amount=350,
                ),
            ),
        )


class FakeFailParser(BankParser):
    """永遠 can_parse=False 的假 parser。"""

    bank_code = "ESUN"
    version = "v1"

    def can_parse(self, pdf_path: Path) -> bool:
        return False

    def parse(self, pdf_path: Path) -> ParseResult:
        raise ParseError("不應被呼叫")


class FakeCanParseButFailParser(BankParser):
    """can_parse=True 但 parse() 失敗的假 parser。"""

    bank_code = "ESUN"
    version = "v2"

    def can_parse(self, pdf_path: Path) -> bool:
        return True

    def parse(self, pdf_path: Path) -> ParseResult:
        raise ParseError("格式不支援")


async def _create_test_session():
    """建立 in-memory DB + session。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


def _make_attachment(
    bank_code: str,
    message_id: str,
    attachment_id: str,
    status: str = "decrypted",
    staged_path: str = "/data/staging/test/bill.pdf",
) -> StagedAttachment:
    return StagedAttachment(
        bank_code=bank_code,
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        message_date=datetime(2026, 3, 10),
        original_filename=f"{attachment_id}.pdf",
        staged_path=staged_path,
        status=status,
    )


def _make_bank_config(
    bank_code: str,
    active_parser_version: str = "v1",
) -> BankConfig:
    return BankConfig(
        bank_code=bank_code,
        bank_name=f"{bank_code} Bank",
        gmail_filter=f"from:{bank_code.lower()}@example.com",
        active_parser_version=active_parser_version,
    )


class TestSuccessfulParse:
    """成功解析流程的整合測試。"""

    async def test_parse_creates_bill_and_transactions(self) -> None:
        """解析成功後建立 Bill 與 Transaction 記錄。"""
        test_registry = _ParserRegistry()
        test_registry.register(FakeSuccessParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("CTBC"))
            session.add(
                _make_attachment(
                    "CTBC", "msg-1", "att-1", staged_path="/tmp/ctbc.pdf"
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            assert summary.parsed_count == 1
            assert summary.failed_count == 0
            assert summary.skipped_count == 0

            # 驗證 Bill 已建立
            bills = (await session.execute(select(Bill))).scalars().all()
            assert len(bills) == 1
            assert bills[0].bank_code == "CTBC"
            assert bills[0].billing_month == "2026-03"
            assert bills[0].total_amount == 5000
            assert bills[0].due_date == date(2026, 4, 15)
            assert bills[0].file_path == "/tmp/ctbc.pdf"

            # 驗證 Transaction 已建立
            txns = (await session.execute(select(Transaction))).scalars().all()
            assert len(txns) == 2
            merchants = {t.merchant for t in txns}
            assert merchants == {"星巴克", "全聯"}

        await engine.dispose()

    async def test_attachment_status_updated_to_parsed(self) -> None:
        """解析成功後附件狀態更新為 parsed。"""
        test_registry = _ParserRegistry()
        test_registry.register(FakeSuccessParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("CTBC"))
            session.add(
                _make_attachment(
                    "CTBC", "msg-1", "att-1", staged_path="/tmp/ctbc.pdf"
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                await run_parse_job(session)

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parsed"
            assert att.error_reason is None

        await engine.dispose()


class TestParseFailure:
    """解析失敗流程的整合測試。"""

    async def test_all_parsers_fail_marks_parse_failed(self) -> None:
        """所有 parser 失敗時附件標記為 parse_failed。"""
        test_registry = _ParserRegistry()
        test_registry.register(FakeFailParser())
        test_registry.register(FakeCanParseButFailParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("ESUN"))
            session.add(
                _make_attachment(
                    "ESUN", "msg-1", "att-1", staged_path="/tmp/esun.pdf"
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            assert summary.parsed_count == 0
            assert summary.failed_count == 1
            assert len(summary.errors) == 1

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parse_failed"
            assert att.error_reason is not None

        await engine.dispose()

    async def test_no_parser_registered_marks_parse_failed(self) -> None:
        """沒有註冊 parser 的銀行標記為 parse_failed。"""
        test_registry = _ParserRegistry()

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("UNKNOWN"))
            session.add(
                _make_attachment(
                    "UNKNOWN", "msg-1", "att-1", staged_path="/tmp/unk.pdf"
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            assert summary.failed_count == 1

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parse_failed"
            assert "找不到 parser" in (att.error_reason or "")

        await engine.dispose()

    async def test_single_failure_does_not_abort_batch(self) -> None:
        """單筆失敗不中止整批。"""
        test_registry = _ParserRegistry()
        test_registry.register(FakeSuccessParser())
        # ESUN 沒有 parser，會 fail

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("CTBC"))
            session.add(_make_bank_config("ESUN"))
            session.add(
                _make_attachment(
                    "ESUN", "msg-1", "att-1", staged_path="/tmp/esun.pdf"
                )
            )
            session.add(
                _make_attachment(
                    "CTBC", "msg-2", "att-2", staged_path="/tmp/ctbc.pdf"
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            assert summary.failed_count == 1
            assert summary.parsed_count == 1

        await engine.dispose()


class TestDeduplication:
    """去重複保護的整合測試。"""

    async def test_duplicate_bill_skips_creation(self) -> None:
        """同銀行同月份帳單已存在時，略過建立並標記為 parsed。"""
        test_registry = _ParserRegistry()
        test_registry.register(FakeSuccessParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("CTBC"))
            # 預先建立 Bill
            session.add(
                Bill(
                    bank_code="CTBC",
                    billing_month="2026-03",
                    total_amount=5000,
                    due_date=date(2026, 4, 15),
                )
            )
            session.add(
                _make_attachment(
                    "CTBC", "msg-1", "att-1", staged_path="/tmp/ctbc.pdf"
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            assert summary.parsed_count == 0
            assert summary.skipped_count == 1

            # 不應建立重複的 Bill
            bills = (await session.execute(select(Bill))).scalars().all()
            assert len(bills) == 1

            # 附件狀態應更新為 parsed
            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_attachment_id == "att-1"
            )
            att = (await session.execute(stmt)).scalar_one()
            assert att.status == "parsed"

        await engine.dispose()

    async def test_already_parsed_attachment_not_reprocessed(self) -> None:
        """已為 parsed 狀態的附件不會再次被查詢到。"""
        test_registry = _ParserRegistry()
        test_registry.register(FakeSuccessParser())

        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            session.add(_make_bank_config("CTBC"))
            session.add(
                _make_attachment(
                    "CTBC", "msg-1", "att-1",
                    status="parsed",
                    staged_path="/tmp/ctbc.pdf",
                )
            )
            await session.commit()

            with patch("ccas.parser.job.registry", test_registry):
                summary = await run_parse_job(session)

            # 因為狀態不是 decrypted，所以不會被處理
            assert summary.parsed_count == 0
            assert summary.skipped_count == 0
            assert summary.failed_count == 0

        await engine.dispose()

    async def test_empty_batch_returns_zero_summary(self) -> None:
        """沒有待解析附件時回傳全零 summary。"""
        engine, session_factory = await _create_test_session()
        async with session_factory() as session:
            summary = await run_parse_job(session)

            assert summary.parsed_count == 0
            assert summary.skipped_count == 0
            assert summary.failed_count == 0

        await engine.dispose()
