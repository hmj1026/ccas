"""E2E 測試：pipeline 成功路徑。

以 mocked 外部服務（Gmail、Telegram）搭配真實 in-memory SQLite 資料庫，
驗證各 staging 狀態轉換與最終產出。
"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import (
    BankConfig,
    Bill,
    StagedAttachment,
    Transaction,
)


@pytest.mark.asyncio
class TestIngestStage:
    """3.2: mock Gmail API，驗證 staging record 正確建立。"""

    async def test_ingest_creates_staged_record(
        self, db_session: AsyncSession, bank_config: BankConfig, staging_dir: str
    ) -> None:
        from ccas.ingestor.gmail_client import GmailAttachmentMeta, GmailMessage

        fake_attachment = GmailAttachmentMeta(
            message_id="msg-100",
            attachment_id="att-100",
            filename="202603_statement.pdf",
            message_date=datetime(2026, 3, 15),
            size=1024,
        )
        fake_message = GmailMessage(
            message_id="msg-100",
            message_date=datetime(2026, 3, 15),
            pdf_attachments=(fake_attachment,),
        )

        staged_file = (
            Path(staging_dir) / "TESTBANK" / "msg-100_2026_202603_statement.pdf"
        )

        mock_settings = MagicMock()
        mock_settings.staging_dir = staging_dir

        with (
            patch("ccas.ingestor.job.load_credentials") as mock_creds,
            patch("ccas.ingestor.job.build_gmail_service") as mock_svc,
            patch("ccas.ingestor.job.search_messages", return_value=[fake_message]),
            patch("ccas.ingestor.job.download_attachment", return_value=b"%PDF-fake"),
            patch(
                "ccas.ingestor.job.build_staged_path",
                return_value=staged_file,
            ),
            patch("ccas.ingestor.job.get_settings", return_value=mock_settings),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.write_bytes"),
        ):
            mock_creds.return_value = MagicMock()
            mock_svc.return_value = MagicMock()

            from ccas.ingestor.job import run_ingestion_job

            summary = await run_ingestion_job(db_session)

        assert summary.staged_count == 1
        assert summary.failed_count == 0

        result = await db_session.execute(select(StagedAttachment))
        records = list(result.scalars().all())
        assert len(records) == 1
        assert records[0].status == "staged"
        assert records[0].gmail_message_id == "msg-100"
        assert records[0].bank_code == "TESTBANK"


@pytest.mark.asyncio
class TestDecryptStage:
    """3.3: mock 解密流程，驗證 status 轉換至 decrypted。"""

    async def test_decrypt_updates_status_to_decrypted(
        self, db_session: AsyncSession, staged_attachment: StagedAttachment
    ) -> None:
        from ccas.decryptor.decrypt import DecryptResult

        with (
            patch(
                "ccas.decryptor.job.decrypt_pdf_multi",
                return_value=DecryptResult(needed_decryption=True),
            ),
            patch(
                "ccas.decryptor.job.resolve_passwords",
                return_value=("test-password",),
            ),
        ):
            from ccas.decryptor.job import run_decryption_job

            summary = await run_decryption_job(db_session)

        assert summary.decrypted_count == 1
        assert summary.failed_count == 0

        await db_session.refresh(staged_attachment)
        assert staged_attachment.status == "decrypted"


@pytest.mark.asyncio
class TestParseStage:
    """3.4: mock 解析流程，驗證 bills/transactions 正確建立。"""

    async def test_parse_creates_bill_and_transactions(
        self, db_session: AsyncSession, decrypted_attachment: StagedAttachment
    ) -> None:
        from ccas.parser.result import ParseResult, TransactionItem

        fake_result = ParseResult(
            bank_code="TESTBANK",
            billing_month="2026-03",
            total_amount=15000,
            due_date=date(2026, 4, 15),
            transactions=(
                TransactionItem(
                    trans_date=date(2026, 3, 1),
                    merchant="超商購物",
                    amount=500,
                ),
                TransactionItem(
                    trans_date=date(2026, 3, 5),
                    merchant="加油站",
                    amount=1200,
                ),
            ),
        )

        mock_parser = MagicMock()
        mock_parser.bank_code = "TESTBANK"
        mock_parser.version = "v1"
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = fake_result

        with patch(
            "ccas.parser.job.registry.resolve",
            return_value=[mock_parser],
        ):
            from ccas.parser.job import run_parse_job

            summary = await run_parse_job(db_session)

        assert summary.parsed_count == 1
        assert summary.failed_count == 0

        await db_session.refresh(decrypted_attachment)
        assert decrypted_attachment.status == "parsed"

        # 驗證 bills 記錄
        bills_result = await db_session.execute(select(Bill))
        bills = list(bills_result.scalars().all())
        assert len(bills) == 1
        assert bills[0].bank_code == "TESTBANK"
        assert bills[0].billing_month == "2026-03"
        assert bills[0].total_amount == 15000

        # 驗證 transactions 記錄
        txn_result = await db_session.execute(select(Transaction))
        txns = list(txn_result.scalars().all())
        assert len(txns) == 2
        merchants = {t.merchant for t in txns}
        assert merchants == {"超商購物", "加油站"}


@pytest.mark.asyncio
class TestNotifyStage:
    """3.5: mock Telegram API，驗證通知送出且包含帳單摘要。"""

    async def test_notify_sends_correct_summary(
        self, db_session: AsyncSession, bank_config: BankConfig
    ) -> None:
        bill = Bill(
            bank_code="TESTBANK",
            billing_month="2026-03",
            total_amount=15000,
            due_date=date(2026, 4, 15),
        )
        db_session.add(bill)
        await db_session.commit()

        mock_send = AsyncMock()

        with patch("ccas.bot.job.send_message", mock_send):
            from ccas.bot.job import run_notify_job

            summary = await run_notify_job(db_session)

        assert summary.sent_count == 1
        assert summary.failed_count == 0

        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][2]
        assert "測試銀行" in sent_text
        assert "2026-03" in sent_text
        assert "15,000" in sent_text
