"""Web-fetch integration tests: _process_web_fetch with mock fetcher."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.fetcher.base import BankFetcher
from ccas.ingestor.fetcher.registry import _FetcherRegistry
from ccas.ingestor.gmail_client import GmailMessage
from ccas.ingestor.job import IngestionSummary, _process_web_fetch
from ccas.storage.models import Base, StagedAttachment

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("API_TOKEN", "test")

_FAKE_PDF = b"%PDF-1.4 fake content"
_HTML_BODY = "<html><body><a>Download Bill</a></body></html>"


class _MockFetcher(BankFetcher):
    """Mock BankFetcher that always returns fixed PDF bytes."""

    @property
    def bank_code(self) -> str:
        return "MOCKBANK"

    def can_fetch(self, html_body: str) -> bool:
        return bool(html_body)

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        return _FAKE_PDF


async def _create_test_session():
    """Create in-memory DB + session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


def _mock_settings():
    """Create a mock Settings object with required attributes."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.staging_dir = "/tmp/test_web_fetch_staging"
    settings.get_bank_credential.return_value = "test-value"
    return settings


def _web_fetch_message(
    message_id: str = "msg-web-001",
) -> GmailMessage:
    """Create a GmailMessage with html_body (no PDF attachments)."""
    return GmailMessage(
        message_id=message_id,
        message_date=datetime(2026, 4, 1),
        pdf_attachments=(),
        html_body=_HTML_BODY,
    )


class TestProcessWebFetch:
    """_process_web_fetch() integration tests."""

    async def test_creates_staged_record_with_web_fetch_source(self, tmp_path: Path):
        """Successful web-fetch creates StagedAttachment with web_fetch source."""
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_MockFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            summary = IngestionSummary()
            message = _web_fetch_message()

            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary,
                )

            await session.commit()

            stmt = select(StagedAttachment).where(
                StagedAttachment.bank_code == "MOCKBANK"
            )
            result = await session.execute(stmt)
            records = list(result.scalars().all())

            assert len(records) == 1
            record = records[0]
            assert record.source_type == "web_fetch"
            assert record.status == "staged"
            assert record.gmail_attachment_id == "web_fetch_msg-web-001"
            assert summary.staged_count == 1

        await engine.dispose()

    async def test_synthetic_attachment_id(self, tmp_path: Path):
        """Web-fetch uses 'web_fetch_{message_id}' as the synthetic attachment ID."""
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_MockFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            summary = IngestionSummary()
            message = _web_fetch_message("msg-synth-test")

            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary,
                )

            await session.commit()

            stmt = select(StagedAttachment)
            result = await session.execute(stmt)
            record = result.scalar_one()
            assert record.gmail_attachment_id == "web_fetch_msg-synth-test"

        await engine.dispose()

    async def test_dedup_skips_second_call(self, tmp_path: Path):
        """Calling _process_web_fetch twice for the same message skips the second."""
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_MockFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            message = _web_fetch_message("msg-dedup")

            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                summary1 = IngestionSummary()
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary1,
                )
                await session.commit()

                summary2 = IngestionSummary()
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary2,
                )

            assert summary1.staged_count == 1
            assert summary2.skipped_count == 1

            stmt = select(StagedAttachment)
            result = await session.execute(stmt)
            records = list(result.scalars().all())
            assert len(records) == 1

        await engine.dispose()

    async def test_no_fetcher_registered_skips(self, tmp_path: Path):
        """When no fetcher is registered for the bank, nothing happens."""
        engine, session_factory = await _create_test_session()
        empty_registry = _FetcherRegistry()

        settings = _mock_settings()

        async with session_factory() as session:
            summary = IngestionSummary()
            message = _web_fetch_message()

            with patch("ccas.ingestor.fetcher.fetcher_registry", empty_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary,
                )

            assert summary.staged_count == 0
            assert summary.skipped_count == 0

        await engine.dispose()

    async def test_writes_pdf_to_staging_dir(self, tmp_path: Path):
        """PDF bytes are written to the staging directory."""
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_MockFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            summary = IngestionSummary()
            message = _web_fetch_message("msg-write-test")

            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary,
                )

            await session.commit()

            # Verify a PDF file was written
            pdf_files = list(tmp_path.rglob("*.pdf"))
            assert len(pdf_files) == 1
            assert pdf_files[0].read_bytes() == _FAKE_PDF

        await engine.dispose()

    async def test_retry_does_not_delete_newly_written_file(self, tmp_path: Path):
        """Force retry to the same path must not delete the newly written PDF."""
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_MockFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            message = _web_fetch_message("msg-retry-nodelete")

            # First call: stage the file
            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    IngestionSummary(),
                )
            await session.commit()

            # Second call with force=True: retry to the exact same path
            second_summary = IngestionSummary()
            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    second_summary,
                    force=True,
                )
            await session.commit()

            # File must still exist on disk after retry
            pdf_files = list(tmp_path.rglob("*.pdf"))
            assert len(pdf_files) == 1
            assert pdf_files[0].read_bytes() == _FAKE_PDF
            assert second_summary.staged_count == 1

        await engine.dispose()


class _RecordNotFoundFetcher(BankFetcher):
    """Mock fetcher that simulates FUBON record_not_found (expired link)."""

    @property
    def bank_code(self) -> str:
        return "MOCKBANK"

    def can_fetch(self, html_body: str) -> bool:
        return bool(html_body)

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        from ccas.ingestor.fetcher.base import FetchError

        raise FetchError(
            "MOCKBANK",
            "record_not_found: doLogin msg='查無資料'",
        )


class _GenericFailureFetcher(BankFetcher):
    """Mock fetcher that fails with a non-expired error."""

    @property
    def bank_code(self) -> str:
        return "MOCKBANK"

    def can_fetch(self, html_body: str) -> bool:
        return bool(html_body)

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        from ccas.ingestor.fetcher.base import FetchError

        raise FetchError("MOCKBANK", "captcha_retry_exhausted: 7 attempts failed")


class TestFetchExpiredStatus:
    """Web-fetch failure path: record_not_found → status=fetch_expired."""

    async def test_record_not_found_creates_fetch_expired_record(self, tmp_path: Path):
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_RecordNotFoundFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            summary = IngestionSummary()
            message = _web_fetch_message("msg-expired-001")

            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary,
                )
            await session.commit()

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_message_id == "msg-expired-001"
            )
            record = (await session.execute(stmt)).scalar_one()
            assert record.status == "fetch_expired"
            assert record.error_reason is not None
            assert "fetch_expired" in record.error_reason
            assert summary.failed_count == 0
            assert summary.skipped_count == 1
            assert len(summary.errors) == 0

        await engine.dispose()

    async def test_other_failure_still_creates_failed_record(self, tmp_path: Path):
        engine, session_factory = await _create_test_session()
        mock_registry = _FetcherRegistry()
        mock_registry.register(_GenericFailureFetcher())

        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            summary = IngestionSummary()
            message = _web_fetch_message("msg-generic-fail")

            with patch("ccas.ingestor.fetcher.fetcher_registry", mock_registry):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    message,
                    str(tmp_path),
                    settings,
                    summary,
                )
            await session.commit()

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_message_id == "msg-generic-fail"
            )
            record = (await session.execute(stmt)).scalar_one()
            assert record.status == "failed"
            assert "captcha_retry_exhausted" in (record.error_reason or "")

        await engine.dispose()

    async def test_retry_upgrades_failed_to_fetch_expired(self, tmp_path: Path):
        """既有 failed 記錄若重試再遇 record_not_found，應升級為 fetch_expired。"""
        engine, session_factory = await _create_test_session()
        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            # 先用 generic failure 建立 failed 記錄
            reg1 = _FetcherRegistry()
            reg1.register(_GenericFailureFetcher())
            with patch("ccas.ingestor.fetcher.fetcher_registry", reg1):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    _web_fetch_message("msg-retry"),
                    str(tmp_path),
                    settings,
                    IngestionSummary(),
                )
            await session.commit()

            # 再用 record_not_found 重試（is_failed_retry path）
            reg2 = _FetcherRegistry()
            reg2.register(_RecordNotFoundFetcher())
            with patch("ccas.ingestor.fetcher.fetcher_registry", reg2):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    _web_fetch_message("msg-retry"),
                    str(tmp_path),
                    settings,
                    IngestionSummary(),
                )
            await session.commit()

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_message_id == "msg-retry"
            )
            record = (await session.execute(stmt)).scalar_one()
            assert record.status == "fetch_expired"
            assert "fetch_expired" in (record.error_reason or "")

        await engine.dispose()

    async def test_fetch_expired_not_auto_retried(self, tmp_path: Path):
        """status='fetch_expired' 的紀錄下次 ingest 應跳過（不走 is_failed_retry）。"""
        engine, session_factory = await _create_test_session()
        settings = _mock_settings()
        settings.staging_dir = str(tmp_path)

        async with session_factory() as session:
            reg_expire = _FetcherRegistry()
            reg_expire.register(_RecordNotFoundFetcher())
            with patch("ccas.ingestor.fetcher.fetcher_registry", reg_expire):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    _web_fetch_message("msg-no-retry"),
                    str(tmp_path),
                    settings,
                    IngestionSummary(),
                )
            await session.commit()

            # 第二次使用 success fetcher，若不當重試會變 staged
            reg_ok = _FetcherRegistry()
            reg_ok.register(_MockFetcher())
            second_summary = IngestionSummary()
            with patch("ccas.ingestor.fetcher.fetcher_registry", reg_ok):
                await _process_web_fetch(
                    session,
                    "MOCKBANK",
                    _web_fetch_message("msg-no-retry"),
                    str(tmp_path),
                    settings,
                    second_summary,
                )
            await session.commit()

            stmt = select(StagedAttachment).where(
                StagedAttachment.gmail_message_id == "msg-no-retry"
            )
            record = (await session.execute(stmt)).scalar_one()
            # 應保留 fetch_expired，不被重新下載覆蓋
            assert record.status == "fetch_expired"
            assert second_summary.skipped_count == 1
            assert second_summary.staged_count == 0

        await engine.dispose()
