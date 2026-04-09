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
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")
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
