"""Pipeline Agent query services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.identity import contains_sensitive_data, sanitize_text
from ccas.services.schemas import (
    AgentQueryError,
    PipelineStageSummary,
    PipelineStatus,
    PipelineStatusResult,
    ServiceProjection,
)
from ccas.storage.agent_queries import (
    get_latest_pipeline_run,
    get_pipeline_run_by_id,
    list_pipeline_runs_query,
)
from ccas.storage.models import (
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
)

ALLOWED_PARAM_TYPES: dict[str, type] = {
    "force": bool,
    "bank_code": str,
    "year": int,
    "month": str,
    "from_stage": str,
    "to_stage": str,
}


def _sanitize_pipeline_params(raw_params: Any) -> dict[str, Any]:
    """Whitelist only permitted pipeline options and verify their types."""
    if not isinstance(raw_params, dict):
        return {}

    sanitized: dict[str, Any] = {}
    for key, expected_type in ALLOWED_PARAM_TYPES.items():
        if key in raw_params:
            val = raw_params[key]
            if expected_type is int:
                if isinstance(val, int) and not isinstance(val, bool):
                    sanitized[key] = val
            elif expected_type is bool:
                if isinstance(val, bool):
                    sanitized[key] = val
            elif isinstance(val, expected_type):
                if isinstance(val, str) and contains_sensitive_data(val):
                    val = sanitize_text(val)
                sanitized[key] = val

    return sanitized


def _sanitize_stage_summary(raw_summary: Any) -> list[PipelineStageSummary]:
    """Convert raw stage summaries into safe generic messages with accurate counts."""
    if not isinstance(raw_summary, list):
        return []

    results: list[PipelineStageSummary] = []
    for item in raw_summary:
        if not isinstance(item, dict):
            continue

        stage = str(item.get("stage", ""))
        if contains_sensitive_data(stage):
            raise AgentQueryError(
                "needs_human",
                "Pipeline stage contains sensitive information requiring human review.",
                needs_human=True,
            )

        ok = int(item.get("ok", 0))
        fail = int(item.get("fail", 0))
        elapsed_ms = int(item.get("elapsed_ms", 0))

        raw_counts = item.get("counts", {})
        counts: dict[str, int] = {}
        if isinstance(raw_counts, dict):
            for k, v in raw_counts.items():
                k_str = str(k)
                if contains_sensitive_data(k_str):
                    raise AgentQueryError(
                        "needs_human",
                        "Pipeline count key contains sensitive information.",
                        needs_human=True,
                    )
                if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                    raise AgentQueryError(
                        "needs_human",
                        "Pipeline counts must be nonnegative integers.",
                        needs_human=True,
                    )
                counts[k_str] = v

        raw_errors = item.get("errors", [])
        errors: list[str] = []
        if isinstance(raw_errors, list) and raw_errors:
            for _ in raw_errors:
                errors.append(
                    f"Stage processing failure ({fail} failed item(s)); "
                    "manual review and check required."
                )
        elif fail > 0:
            errors.append(
                f"Stage encountered {fail} failure(s); "
                "manual review and check required."
            )

        try:
            results.append(
                PipelineStageSummary(
                    stage=stage,
                    ok=ok,
                    fail=fail,
                    elapsed_ms=elapsed_ms,
                    counts=counts,
                    errors=errors,
                )
            )
        except Exception as exc:
            raise AgentQueryError(
                "needs_human",
                (
                    "Database contains malformed stage summary data; "
                    "human review required."
                ),
                needs_human=True,
            ) from exc

    return results


def _derive_pipeline_error_message(
    status_val: str,
    term_val: str | None,
    has_error: bool,
) -> str | None:
    """Derive fixed actionable generic error text from status/terminal_reason only."""
    if not has_error and status_val not in ("failed", "cancelled"):
        return None

    if term_val == "retries_exhausted":
        return (
            "Pipeline execution failed after retries were exhausted; "
            "manual review and check required."
        )
    if term_val == "stage_failure":
        return (
            "Pipeline execution failed during stage processing; "
            "manual review and check required."
        )
    if term_val == "worker_exception":
        return (
            "Pipeline worker encountered an unhandled error; "
            "manual review and check required."
        )
    if term_val == "enqueue_failure":
        return "Pipeline enqueue failed; manual review and check required."
    if term_val == "cancelled" or status_val == "cancelled":
        return "Pipeline execution was cancelled."
    if status_val == "failed":
        return "Pipeline execution failed; manual review and check required."
    return "Pipeline execution encountered an error; manual review and check required."


async def pipeline_status(
    session: AsyncSession,
) -> ServiceProjection[PipelineStatusResult]:
    """Fetch status of the most recent pipeline run."""
    run = await get_latest_pipeline_run(session)
    if run is None:
        raise AgentQueryError("resource_not_found", "No pipeline runs found.")

    status_val = (
        run.status.value
        if isinstance(run.status, PipelineRunStatus)
        else str(run.status)
    )

    term_val = (
        run.terminal_reason.value
        if isinstance(run.terminal_reason, PipelineRunTerminalReason)
        else (str(run.terminal_reason) if run.terminal_reason is not None else None)
    )

    needs_human = status_val == "failed" and term_val == "retries_exhausted"

    for field_name, field_val in [
        ("id", run.id),
        ("job_id", run.job_id),
        ("triggered_by", run.triggered_by),
        ("current_stage", run.current_stage),
    ]:
        if field_val and contains_sensitive_data(field_val):
            raise AgentQueryError(
                "needs_human",
                f"Pipeline {field_name} contains sensitive information.",
                needs_human=True,
            )

    safe_params = _sanitize_pipeline_params(run.params)
    stage_summary_list = _sanitize_stage_summary(run.stage_summary)

    safe_error_msg = _derive_pipeline_error_message(
        status_val, term_val, bool(run.error_message)
    )

    try:
        payload = PipelineStatus(
            id=run.id,
            job_id=run.job_id,
            status=status_val,  # type: ignore[arg-type]
            triggered_by=run.triggered_by,
            params=safe_params,
            current_stage=run.current_stage,
            current_stage_processed=run.current_stage_processed,
            current_stage_total=run.current_stage_total,
            stage_summary=stage_summary_list,
            error_message=safe_error_msg,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
            needs_human=needs_human,
        )
    except Exception as exc:
        raise AgentQueryError(
            "needs_human",
            "Database contains malformed pipeline data; human review required.",
            needs_human=True,
        ) from exc

    rest_metadata = {
        "raw_params": run.params,
        "raw_error_message": run.error_message,
        "raw_stage_summary": run.stage_summary,
    }

    return ServiceProjection(
        payload=PipelineStatusResult(data=payload),
        rest_metadata=rest_metadata,
    )


@dataclass
class PipelineRunSnapshot:
    """Internal compatibility snapshot for a pipeline run."""

    id: str
    job_id: str
    status: str
    triggered_by: str
    params: dict[str, Any]
    current_stage: str | None
    current_stage_processed: int
    current_stage_total: int
    stage_summary: list[dict[str, Any]]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class PipelineRunsPageSnapshot:
    """Internal compatibility snapshot for a page of pipeline runs."""

    runs: list[PipelineRunSnapshot]
    total: int


def _to_run_snapshot(run: PipelineRun) -> PipelineRunSnapshot:
    status_val = (
        run.status.value
        if isinstance(run.status, PipelineRunStatus)
        else str(run.status)
    )
    return PipelineRunSnapshot(
        id=run.id,
        job_id=run.job_id,
        status=status_val,
        triggered_by=run.triggered_by,
        params=run.params if isinstance(run.params, dict) else {},
        current_stage=run.current_stage,
        current_stage_processed=run.current_stage_processed,
        current_stage_total=run.current_stage_total,
        stage_summary=run.stage_summary if isinstance(run.stage_summary, list) else [],
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


async def list_pipeline_runs(
    session: AsyncSession,
    *,
    status: str | PipelineRunStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ServiceProjection[PipelineRunsPageSnapshot]:
    """Fetch paginated pipeline runs for REST compatibility."""
    rows, total = await list_pipeline_runs_query(
        session, status=status, page=page, page_size=page_size
    )
    snapshots = [_to_run_snapshot(row) for row in rows]
    rest_metadata = {
        "raw_summaries": [
            {
                "id": s.id,
                "job_id": s.job_id,
                "status": s.status,
                "triggered_by": s.triggered_by,
                "params": s.params,
                "current_stage": s.current_stage,
                "current_stage_processed": s.current_stage_processed,
                "current_stage_total": s.current_stage_total,
                "stage_summary": s.stage_summary,
                "error_message": s.error_message,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in snapshots
        ],
        "total": total,
    }
    return ServiceProjection(
        payload=PipelineRunsPageSnapshot(runs=snapshots, total=total),
        rest_metadata=rest_metadata,
    )


async def get_pipeline_run(
    session: AsyncSession,
    run_id: str,
) -> ServiceProjection[PipelineRunSnapshot]:
    """Fetch single pipeline run by ID for REST compatibility."""
    run = await get_pipeline_run_by_id(session, run_id)
    if run is None:
        raise AgentQueryError("resource_not_found", f"找不到執行紀錄 #{run_id}")

    snapshot = _to_run_snapshot(run)
    rest_metadata = {
        "raw_summary": {
            "id": snapshot.id,
            "job_id": snapshot.job_id,
            "status": snapshot.status,
            "triggered_by": snapshot.triggered_by,
            "params": snapshot.params,
            "current_stage": snapshot.current_stage,
            "current_stage_processed": snapshot.current_stage_processed,
            "current_stage_total": snapshot.current_stage_total,
            "stage_summary": snapshot.stage_summary,
            "error_message": snapshot.error_message,
            "started_at": snapshot.started_at,
            "completed_at": snapshot.completed_at,
            "created_at": snapshot.created_at,
            "updated_at": snapshot.updated_at,
        }
    }
    return ServiceProjection(
        payload=snapshot,
        rest_metadata=rest_metadata,
    )
