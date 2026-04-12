"""E2E 測試：pipeline 錯誤路徑。

驗證單筆失敗不中斷同批次其他項目的處理，
以及錯誤被正確記錄至日誌與 DB。
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.decryptor.decrypt import DecryptionError
from ccas.storage.models import (
    BankConfig,
    Bill,
    StagedAttachment,
    Transaction,
)


@pytest.mark.asyncio
class TestDecryptFailureIsolation:
    """4.1: 單一附件解密失敗，同批次其他附件不受中斷。"""

    async def test_decrypt_failure_does_not_block_others(
        self, db_session: AsyncSession, bank_config: BankConfig
    ) -> None:
        # 建立兩筆 staged 附件
        att_ok = StagedAttachment(
            bank_code="TESTBANK",
            gmail_message_id="msg-ok",
            gmail_attachment_id="att-ok",
            message_date=datetime(2026, 3, 1),
            original_filename="good.pdf",
            staged_path="/tmp/test/good.pdf",
            status="staged",
        )
        att_fail = StagedAttachment(
            bank_code="TESTBANK",
            gmail_message_id="msg-fail",
            gmail_attachment_id="att-fail",
            message_date=datetime(2026, 3, 1),
            original_filename="bad.pdf",
            staged_path="/tmp/test/bad.pdf",
            status="staged",
        )
        db_session.add_all([att_ok, att_fail])
        await db_session.commit()

        from ccas.decryptor.decrypt import DecryptResult

        def mock_decrypt(pdf_path, passwords):
            if "bad.pdf" in str(pdf_path):
                raise DecryptionError("Invalid password")
            return DecryptResult(needed_decryption=True)

        with (
            patch("ccas.decryptor.job.decrypt_pdf_multi", side_effect=mock_decrypt),
            patch("ccas.decryptor.job.resolve_passwords", return_value=("pw",)),
        ):
            from ccas.decryptor.job import run_decryption_job

            summary = await run_decryption_job(db_session)

        assert summary.decrypted_count == 1
        assert summary.failed_count == 1

        await db_session.refresh(att_ok)
        await db_session.refresh(att_fail)
        assert att_ok.status == "decrypted"
        assert att_fail.status == "decrypt_failed"
        assert att_fail.error_reason is not None


@pytest.mark.asyncio
class TestParseFailureIsolation:
    """4.2: 單一附件解析失敗，分類與通知流程繼續處理其餘帳單。"""

    async def test_parse_failure_does_not_block_others(
        self, db_session: AsyncSession, bank_config: BankConfig
    ) -> None:
        from ccas.parser.result import ParseResult, TransactionItem

        att_ok = StagedAttachment(
            bank_code="TESTBANK",
            gmail_message_id="msg-parse-ok",
            gmail_attachment_id="att-parse-ok",
            message_date=datetime(2026, 3, 1),
            original_filename="good.pdf",
            staged_path="/tmp/test/good.pdf",
            status="decrypted",
        )
        att_fail = StagedAttachment(
            bank_code="TESTBANK",
            gmail_message_id="msg-parse-fail",
            gmail_attachment_id="att-parse-fail",
            message_date=datetime(2026, 3, 1),
            original_filename="bad.pdf",
            staged_path="/tmp/test/bad.pdf",
            status="decrypted",
        )
        db_session.add_all([att_ok, att_fail])
        await db_session.commit()

        good_result = ParseResult(
            bank_code="TESTBANK",
            billing_month="2026-03",
            total_amount=10000,
            due_date=date(2026, 4, 15),
            transactions=(
                TransactionItem(
                    trans_date=date(2026, 3, 1),
                    merchant="超商",
                    amount=300,
                ),
            ),
        )

        mock_parser = MagicMock()
        mock_parser.bank_code = "TESTBANK"
        mock_parser.version = "v1"

        call_count = 0

        def mock_can_parse(pdf_path):
            return True

        def mock_parse(pdf_path):
            nonlocal call_count
            call_count += 1
            if "bad.pdf" in str(pdf_path):
                from ccas.parser.base import ParseError

                raise ParseError("corrupt PDF")
            return good_result

        mock_parser.can_parse = mock_can_parse
        mock_parser.parse = mock_parse

        with patch(
            "ccas.parser.job.registry.resolve",
            return_value=[mock_parser],
        ):
            from ccas.parser.job import run_parse_job

            summary = await run_parse_job(db_session)

        assert summary.parsed_count == 1
        assert summary.failed_count == 1

        await db_session.refresh(att_ok)
        await db_session.refresh(att_fail)
        assert att_ok.status == "parsed"
        assert att_fail.status == "parse_failed"

        # 驗證成功的帳單已建立
        bills = list((await db_session.execute(select(Bill))).scalars().all())
        assert len(bills) == 1

        txns = list((await db_session.execute(select(Transaction))).scalars().all())
        assert len(txns) == 1


@pytest.mark.asyncio
class TestNotifyFailureIsolation:
    """4.3: Telegram 通知失敗，錯誤被記錄且 pipeline 不因此失敗。"""

    async def test_notify_failure_does_not_crash_pipeline(
        self, db_session: AsyncSession, bank_config: BankConfig
    ) -> None:
        bill = Bill(
            bank_code="TESTBANK",
            billing_month="2026-03",
            total_amount=10000,
            due_date=date(2026, 4, 15),
        )
        db_session.add(bill)
        await db_session.commit()

        mock_send = AsyncMock(side_effect=ConnectionError("Telegram API timeout"))

        with patch("ccas.bot.job.send_message", mock_send):
            from ccas.bot.job import run_notify_job

            summary = await run_notify_job(db_session)

        assert summary.sent_count == 0
        assert summary.failed_count == 1
        assert len(summary.errors) == 1
        assert "Telegram" in summary.errors[0] or "通知失敗" in summary.errors[0]
