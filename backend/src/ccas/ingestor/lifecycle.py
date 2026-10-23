"""Durable staging lifecycle shared by statement source adapters."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.ingestor.staging import (
    backfill_part_id,
    create_staged_record,
    delete_staged_record,
    find_existing_staged,
    update_staged_record_failure,
)
from ccas.storage.atomic import atomic_write_bytes
from ccas.storage.models import StagedAttachmentStatus
from ccas.storage.paths import (
    build_staged_path,
    resolve_staged_path,
    staged_path_for_storage,
)

logger = logging.getLogger(__name__)


class StagingDisposition(StrEnum):
    """Durable result of processing one source item."""

    STAGED = "staged"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StagedSource:
    """Source-independent identity and record fields for one statement PDF."""

    bank_code: str
    message_id: str
    part_id: str
    attachment_id: str
    message_date: datetime
    original_filename: str
    source_type: Literal["attachment", "web_fetch"] = "attachment"


@dataclass(frozen=True, slots=True)
class StagingResult:
    """Outcome returned only after the database lifecycle has settled."""

    disposition: StagingDisposition
    error_message: str | None = None


class FetchExpiredError(Exception):
    """A web-fetch adapter identified a permanently expired statement link."""

    def __init__(self, message: str, *, error_reason: str) -> None:
        super().__init__(message)
        self.error_reason = error_reason


class StagingRollbackError(RuntimeError):
    """A source transaction could not be rolled back safely."""


PdfAcquirer = Callable[[], Awaitable[bytes]]


def _failure_message(source: StagedSource, error: Exception) -> str:
    if source.source_type == "web_fetch":
        return f"Web-fetch 失敗 ({source.bank_code}/{source.message_id}): {error}"
    return f"附件下載失敗 ({source.bank_code}/{source.original_filename}): {error}"


async def _rollback(session: AsyncSession, *, context: str) -> None:
    try:
        await session.rollback()
    except Exception as error:
        logger.exception("ingestion rollback failed (%s)", context)
        raise StagingRollbackError(f"ingestion rollback failed ({context})") from error


async def _persist_acquisition_failure(
    session: AsyncSession,
    source: StagedSource,
    existing,
    error: Exception,
    *,
    status: StagedAttachmentStatus,
    error_reason: str,
) -> StagingResult:
    message = _failure_message(source, error)
    try:
        if existing is None:
            await create_staged_record(
                session,
                bank_code=source.bank_code,
                message_id=source.message_id,
                attachment_id=source.attachment_id,
                message_date=source.message_date,
                original_filename=source.original_filename,
                staged_path=None,
                status=status,
                error_reason=error_reason,
                source_type=source.source_type,
                part_id=source.part_id,
            )
        else:
            await update_staged_record_failure(
                session,
                existing,
                status=status,
                error_reason=error_reason,
            )
        await session.commit()
    except Exception as persist_error:
        await _rollback(session, context="persisting acquisition failure")
        combined_message = (
            f"{message}; failure state could not be persisted: {persist_error}"
        )
        logger.error(combined_message, exc_info=True)
        return StagingResult(StagingDisposition.FAILED, combined_message)

    if status == StagedAttachmentStatus.FETCH_EXPIRED:
        logger.warning(message)
        return StagingResult(StagingDisposition.SKIPPED)

    logger.error(message, exc_info=(type(error), error, error.__traceback__))
    return StagingResult(StagingDisposition.FAILED, message)


async def cleanup_staged_file(staging_dir: str, staged_path: str | None) -> None:
    """Remove one safely resolved, no-longer-referenced staged file."""
    if not staged_path:
        return
    try:
        path = resolve_staged_path(staging_dir, staged_path)
    except ValueError:
        logger.warning("staged_path 逃逸 staging 根目錄，跳過刪除：%s", staged_path)
        return
    if path.exists():
        await asyncio.to_thread(path.unlink)
        logger.debug("已刪除舊 staging 檔案：%s", staged_path)


def _same_staged_file(
    staging_dir: str,
    old_staged_path: str | None,
    new_staged_path: str,
) -> bool:
    if old_staged_path is None:
        return False
    try:
        return resolve_staged_path(staging_dir, old_staged_path) == resolve_staged_path(
            staging_dir, new_staged_path
        )
    except ValueError:
        # Equal stored values are still the same reference even if a legacy
        # path is invalid; cleanup will independently reject unsafe paths.
        return old_staged_path == new_staged_path


async def stage_source(
    session: AsyncSession,
    staging_dir: str,
    source: StagedSource,
    acquire_pdf: PdfAcquirer,
    *,
    force: bool = False,
) -> StagingResult:
    """Own dedupe, acquisition, atomic write, persistence and old-file cleanup.

    Source adapters supply immutable statement metadata and one lazy PDF
    acquirer. The returned disposition is ``staged`` only after the record
    commit succeeds. A persistence failure always rolls back before returning
    and is never followed by an attempt to create a failure row in that
    transaction.
    """
    try:
        existing = await find_existing_staged(
            session,
            source.message_id,
            source.part_id,
            source.original_filename,
        )
    except Exception as error:
        await _rollback(session, context="looking up staged source")
        message = _failure_message(source, error)
        logger.error(message, exc_info=(type(error), error, error.__traceback__))
        return StagingResult(StagingDisposition.FAILED, message)

    if existing is not None:
        is_failed_retry = existing.status == "failed"
        if not force and not is_failed_retry:
            try:
                await backfill_part_id(session, existing, source.part_id)
                await session.commit()
            except Exception as error:
                await _rollback(session, context="backfilling staged source")
                message = _failure_message(source, error)
                logger.error(
                    message,
                    exc_info=(type(error), error, error.__traceback__),
                )
                return StagingResult(StagingDisposition.FAILED, message)

            logger.debug(
                "略過已存在的附件：%s/%s",
                source.message_id,
                source.attachment_id,
            )
            return StagingResult(StagingDisposition.SKIPPED)

        if is_failed_retry:
            logger.info(
                "自動重試 failed 附件：%s/%s",
                source.message_id,
                source.attachment_id,
            )
        else:
            logger.info(
                "Force 模式：重新處理 %s/%s",
                source.message_id,
                source.attachment_id,
            )

    # ORM values needed after database calls are copied before any commit or
    # rollback can expire the row.
    old_staged_path = existing.staged_path if existing is not None else None

    try:
        pdf_bytes = await acquire_pdf()
    except FetchExpiredError as error:
        return await _persist_acquisition_failure(
            session,
            source,
            existing,
            error,
            status=StagedAttachmentStatus.FETCH_EXPIRED,
            error_reason=error.error_reason,
        )
    except SQLAlchemyError as error:
        # Acquisition adapters may read credentials from the same session.
        # A database error can leave that transaction unusable, so settle it
        # before returning and do not attempt to persist a failure row through
        # the failed transaction.
        await _rollback(session, context="acquiring staged source")
        message = _failure_message(source, error)
        logger.error(message, exc_info=(type(error), error, error.__traceback__))
        return StagingResult(StagingDisposition.FAILED, message)
    except Exception as error:
        return await _persist_acquisition_failure(
            session,
            source,
            existing,
            error,
            status=StagedAttachmentStatus.FAILED,
            error_reason=str(error),
        )

    try:
        staged_path = build_staged_path(
            staging_dir,
            source.bank_code,
            source.message_id,
            source.original_filename,
        )
        await asyncio.to_thread(
            staged_path.parent.mkdir,
            parents=True,
            exist_ok=True,
        )
        await asyncio.to_thread(atomic_write_bytes, staged_path, pdf_bytes)
        new_staged_path = staged_path_for_storage(staging_dir, staged_path)
    except Exception as error:
        return await _persist_acquisition_failure(
            session,
            source,
            existing,
            error,
            status=StagedAttachmentStatus.FAILED,
            error_reason=str(error),
        )

    try:
        if existing is not None:
            await delete_staged_record(session, existing)
        await create_staged_record(
            session,
            bank_code=source.bank_code,
            message_id=source.message_id,
            attachment_id=source.attachment_id,
            message_date=source.message_date,
            original_filename=source.original_filename,
            staged_path=new_staged_path,
            status=StagedAttachmentStatus.STAGED,
            source_type=source.source_type,
            part_id=source.part_id,
        )
        await session.commit()
    except Exception as error:
        await _rollback(session, context="committing staged source")
        message = _failure_message(source, error)
        logger.error(message, exc_info=(type(error), error, error.__traceback__))
        return StagingResult(StagingDisposition.FAILED, message)

    if old_staged_path and not _same_staged_file(
        staging_dir,
        old_staged_path,
        new_staged_path,
    ):
        try:
            await cleanup_staged_file(staging_dir, old_staged_path)
        except Exception:
            logger.warning(
                "ingest old-file cleanup failed (%s); orphan left on disk, "
                "DB is consistent",
                old_staged_path,
                exc_info=True,
            )

    logger.info(
        "已 staged 附件：%s -> %s",
        source.original_filename,
        staged_path,
    )
    return StagingResult(StagingDisposition.STAGED)
