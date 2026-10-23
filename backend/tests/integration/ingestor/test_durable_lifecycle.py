"""Full ingestion lifecycle contracts across the database and staging files."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.ingestor.fetcher.base import BankFetcher
from ccas.ingestor.fetcher.registry import _FetcherRegistry
from ccas.ingestor.gmail_client import GmailAttachmentMeta, GmailMessage
from ccas.ingestor.job import run_ingestion_job
from ccas.ingestor.lifecycle import StagingRollbackError
from ccas.shared.pipeline_types import PipelineOptions
from ccas.storage.models import BankConfig, Base, StagedAttachment

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("API_TOKEN", "test")

_MESSAGE_DATE = datetime(2026, 3, 10)


class _TestFetcher(BankFetcher):
    @property
    def bank_code(self) -> str:
        return "MOCKBANK"

    def can_fetch(self, html_body: str) -> bool:
        return "<download>" in html_body

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        return f"%PDF {html_body}".encode()


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _messages_for_source(source: str) -> list[GmailMessage]:
    if source == "attachment":
        return [
            GmailMessage(
                message_id="first-message",
                message_date=_MESSAGE_DATE,
                pdf_attachments=(
                    GmailAttachmentMeta(
                        message_id="first-message",
                        attachment_id="first-attachment",
                        filename="first.pdf",
                        message_date=_MESSAGE_DATE,
                        size=10,
                        part_id="1",
                    ),
                ),
            ),
            GmailMessage(
                message_id="second-message",
                message_date=_MESSAGE_DATE,
                pdf_attachments=(
                    GmailAttachmentMeta(
                        message_id="second-message",
                        attachment_id="second-attachment",
                        filename="second.pdf",
                        message_date=_MESSAGE_DATE,
                        size=10,
                        part_id="1",
                    ),
                ),
            ),
        ]

    return [
        GmailMessage(
            message_id="first-message",
            message_date=_MESSAGE_DATE,
            pdf_attachments=(),
            html_body="<download>first</download>",
        ),
        GmailMessage(
            message_id="second-message",
            message_date=_MESSAGE_DATE,
            pdf_attachments=(),
            html_body="<download>second</download>",
        ),
    ]


async def _seed_existing_item(
    session: AsyncSession, source: str, staging_dir: Path
) -> tuple[int, Path]:
    session.add(
        BankConfig(
            bank_code="MOCKBANK",
            bank_name="Mock Bank",
            gmail_filter="from:mockbank",
            is_active=True,
        )
    )
    old_relative_path = "legacy/previous.pdf"
    old_file = staging_dir / old_relative_path
    old_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"previous committed PDF")

    is_web_fetch = source == "web_fetch"
    existing = StagedAttachment(
        bank_code="MOCKBANK",
        gmail_message_id="first-message",
        gmail_attachment_id=(
            "web_fetch_first-message" if is_web_fetch else "old-attachment"
        ),
        gmail_part_id=("web:first-message" if is_web_fetch else "1"),
        message_date=_MESSAGE_DATE,
        original_filename=(
            "MOCKBANK_first-message.pdf" if is_web_fetch else "first.pdf"
        ),
        staged_path=old_relative_path,
        status="staged",
        source_type="web_fetch" if is_web_fetch else "attachment",
    )
    session.add(existing)
    await session.commit()
    return existing.id, old_file


def _patch_ingestion_inputs(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    staging_dir: Path,
) -> None:
    from ccas.ingestor import fetcher as fetcher_package
    from ccas.ingestor import job

    settings = SimpleNamespace(
        gmail_credentials_path="/unused/credentials.json",
        gmail_token_path="/unused/token.json",
        staging_dir=str(staging_dir),
        get_bank_credential=lambda _bank, _key: "",
    )
    messages = _messages_for_source(source)

    def search_messages(*args, **kwargs):
        return messages

    def download_attachment(
        _service: object, message_id: str, attachment_id: str
    ) -> bytes:
        return f"%PDF {message_id}:{attachment_id}".encode()

    async def run_in_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(job, "get_settings", lambda: settings)
    monkeypatch.setattr(job, "load_credentials", lambda *_args: object())
    monkeypatch.setattr(job, "build_gmail_service", lambda _credentials: object())
    monkeypatch.setattr(job, "search_messages", search_messages)
    monkeypatch.setattr(job, "download_attachment", download_attachment)
    monkeypatch.setattr(job.asyncio, "to_thread", run_in_thread)

    if source == "web_fetch":
        registry = _FetcherRegistry()
        registry.register(_TestFetcher())
        monkeypatch.setattr(fetcher_package, "fetcher_registry", registry)


@pytest.mark.parametrize("source", ["attachment", "web_fetch"])
async def test_commit_failure_preserves_previous_file_and_continues_next_item(
    source: str,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    existing_id, old_file = await _seed_existing_item(db_session, source, tmp_path)
    _patch_ingestion_inputs(monkeypatch, source, tmp_path)

    original_commit = db_session.commit
    commit_attempts = 0

    async def fail_first_commit() -> None:
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 1:
            raise RuntimeError("injected commit failure")
        await original_commit()

    monkeypatch.setattr(db_session, "commit", fail_first_commit)

    summary = await run_ingestion_job(db_session, options=PipelineOptions(force=True))

    assert summary.staged_count == 1
    assert summary.failed_count == 1
    assert old_file.read_bytes() == b"previous committed PDF"

    records = list(
        (
            await db_session.execute(
                select(StagedAttachment).order_by(StagedAttachment.gmail_message_id)
            )
        )
        .scalars()
        .all()
    )
    previous = next(record for record in records if record.id == existing_id)
    assert previous.staged_path == "legacy/previous.pdf"
    assert previous.status == "staged"

    next_item = next(
        record for record in records if record.gmail_message_id == "second-message"
    )
    assert next_item.status == "staged"
    assert next_item.staged_path is not None
    next_file = tmp_path / next_item.staged_path
    assert next_file.is_file()


@pytest.mark.parametrize("source", ["attachment", "web_fetch"])
async def test_cleanup_failure_keeps_committed_replacement(
    source: str,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _existing_id, old_file = await _seed_existing_item(db_session, source, tmp_path)
    _patch_ingestion_inputs(monkeypatch, source, tmp_path)

    async def fail_cleanup(*_args) -> None:
        raise OSError("injected cleanup failure")

    from ccas.ingestor import lifecycle

    monkeypatch.setattr(lifecycle, "cleanup_staged_file", fail_cleanup)

    summary = await run_ingestion_job(db_session, options=PipelineOptions(force=True))

    assert summary.staged_count == 2
    assert summary.failed_count == 0
    assert old_file.read_bytes() == b"previous committed PDF"

    records = list((await db_session.execute(select(StagedAttachment))).scalars().all())
    previous = next(
        record for record in records if record.gmail_message_id == "first-message"
    )
    assert previous.staged_path != "legacy/previous.pdf"
    assert previous.status == "staged"
    assert previous.staged_path is not None
    assert (tmp_path / previous.staged_path).is_file()


async def test_commit_rollback_does_not_expire_later_bank_config(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_session.add_all(
        [
            BankConfig(
                bank_code="FIRSTBANK",
                bank_name="First Bank",
                gmail_filter="from:firstbank",
                is_active=True,
            ),
            BankConfig(
                bank_code="SECONDBANK",
                bank_name="Second Bank",
                gmail_filter="from:secondbank",
                is_active=True,
            ),
        ]
    )
    await db_session.commit()
    _patch_ingestion_inputs(monkeypatch, "attachment", tmp_path)

    from ccas.ingestor import job

    first, second = _messages_for_source("attachment")
    monkeypatch.setattr(
        job,
        "search_messages",
        lambda *_args, bank_code, **_kwargs: (
            [first] if bank_code == "FIRSTBANK" else [second]
        ),
    )

    original_commit = db_session.commit
    commit_attempts = 0

    async def fail_first_commit() -> None:
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 1:
            raise RuntimeError("injected first-bank commit failure")
        await original_commit()

    monkeypatch.setattr(db_session, "commit", fail_first_commit)

    summary = await run_ingestion_job(db_session)

    assert summary.failed_count == 1
    assert summary.staged_count == 1
    next_bank_item = await db_session.scalar(
        select(StagedAttachment).where(
            StagedAttachment.gmail_message_id == "second-message"
        )
    )
    assert next_bank_item is not None
    assert next_bank_item.bank_code == "SECONDBANK"
    assert next_bank_item.staged_path is not None
    assert (tmp_path / next_bank_item.staged_path).is_file()


async def test_sqlalchemy_credential_error_rolls_back_and_continues(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_session.add(
        BankConfig(
            bank_code="MOCKBANK",
            bank_name="Mock Bank",
            gmail_filter="from:mockbank",
            is_active=True,
        )
    )
    await db_session.commit()
    _patch_ingestion_inputs(monkeypatch, "web_fetch", tmp_path)

    from ccas.ingestor import job

    credential_lookups = 0

    async def resolve_credential(*_args, **_kwargs) -> str:
        nonlocal credential_lookups
        credential_lookups += 1
        if credential_lookups == 1:
            raise OperationalError(
                "SELECT credential",
                {},
                RuntimeError("credential database unavailable"),
            )
        return ""

    monkeypatch.setattr(job, "resolve_bank_credential", resolve_credential)

    summary = await run_ingestion_job(db_session)

    assert summary.failed_count == 1
    assert summary.staged_count == 1
    records = list((await db_session.execute(select(StagedAttachment))).scalars())
    assert [record.gmail_message_id for record in records] == ["second-message"]
    assert records[0].status == "staged"
    assert records[0].staged_path is not None
    assert (tmp_path / records[0].staged_path).is_file()


async def test_rollback_failure_stops_before_processing_next_item(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_session.add(
        BankConfig(
            bank_code="MOCKBANK",
            bank_name="Mock Bank",
            gmail_filter="from:mockbank",
            is_active=True,
        )
    )
    await db_session.commit()
    _patch_ingestion_inputs(monkeypatch, "attachment", tmp_path)

    from ccas.ingestor import job

    original_download = job.download_attachment
    download_attempts = 0

    def count_download(*args, **kwargs) -> bytes:
        nonlocal download_attempts
        download_attempts += 1
        return original_download(*args, **kwargs)

    monkeypatch.setattr(job, "download_attachment", count_download)

    async def fail_commit() -> None:
        raise RuntimeError("injected commit failure")

    async def fail_rollback() -> None:
        raise RuntimeError("injected rollback failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", fail_rollback)

    with pytest.raises(StagingRollbackError):
        await run_ingestion_job(db_session)

    assert download_attempts == 1
