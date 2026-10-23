"""Own the committed run → queue → job-id submission lifecycle."""

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import (
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
)

logger = logging.getLogger(__name__)


class PipelineQueue(Protocol):
    """Queue seam; the worker must receive a previously committed run id."""

    def enqueue(self, params: dict[str, Any], *, run_id: str) -> str: ...


@dataclass
class RqPipelineQueue:
    """RQ adapter owns worker arguments, retry, timeout and failure callback."""

    queue: Queue

    def enqueue(self, params: dict[str, Any], *, run_id: str) -> str:
        from ccas.pipeline.worker import (
            get_retry,
            on_failure_handler,
            run_pipeline_sync,
        )

        # on_failure_handler reads bank_code from job.args[0].
        job = self.queue.enqueue(
            run_pipeline_sync,
            params,
            run_id=run_id,
            retry=get_retry(),
            on_failure=on_failure_handler,
            job_timeout="30m",
        )
        return job.id


@dataclass(frozen=True)
class PipelineSubmission:
    run_id: str
    job_id: str


class PipelineEnqueueError(Exception):
    """Queue rejected submission after its failed run was persisted."""

    def __init__(self, run_id: str, message: str, cause: Exception) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.cause = cause


async def submit_pipeline(
    session: AsyncSession,
    queue: PipelineQueue,
    params: dict[str, Any],
    *,
    triggered_by: str,
) -> PipelineSubmission:
    """Commit a queued run, submit it, then persist the queue's job id.

    Only enqueue exceptions become ENQUEUE_FAILURE. Database failures propagate
    unchanged: a job-id write failure must not label a possibly running job as
    rejected. This does not make SQLite and Redis one atomic transaction.
    """
    run_id = str(uuid4())
    session.add(
        PipelineRun(
            id=run_id,
            job_id=run_id,
            status=PipelineRunStatus.QUEUED,
            triggered_by=triggered_by,
            params=params,
            stage_summary=[],
        )
    )
    await session.commit()

    try:
        job_id = queue.enqueue(params, run_id=run_id)
    except Exception as exc:
        logger.exception("Pipeline enqueue failed (run_id=%s)", run_id)
        # Preserve each existing entry point's stored/public error text.
        message = (
            "Pipeline enqueue failed (scheduler)"
            if triggered_by == "scheduler"
            else f"Pipeline enqueue failed: {exc}"
        )
        run = await session.get(PipelineRun, run_id)
        if run is not None:
            run.status = PipelineRunStatus.FAILED
            run.terminal_reason = PipelineRunTerminalReason.ENQUEUE_FAILURE
            run.error_message = message
            await session.commit()
        raise PipelineEnqueueError(run_id, message, exc) from exc

    run = await session.get(PipelineRun, run_id)
    if run is not None:
        run.job_id = job_id
        await session.commit()
    return PipelineSubmission(run_id=run_id, job_id=job_id)
