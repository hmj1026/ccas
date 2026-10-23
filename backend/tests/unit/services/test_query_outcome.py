"""Shared tool-result policy for the read-only Agent adapters."""

from __future__ import annotations

from datetime import datetime

import pytest

from ccas.services.query_outcome import require_tool_result
from ccas.services.schemas import (
    AgentQueryError,
    PipelineStatus,
    PipelineStatusResult,
    ServiceProjection,
)


def _pipeline_projection(
    *, needs_human: bool
) -> ServiceProjection[PipelineStatusResult]:
    now = datetime(2026, 4, 1, 12, 0, 0)
    return ServiceProjection(
        payload=PipelineStatusResult(
            data=PipelineStatus(
                id="run-123",
                job_id="job-123",
                status="failed" if needs_human else "succeeded",
                triggered_by="api",
                params={},
                current_stage="parse",
                current_stage_processed=0,
                current_stage_total=1,
                stage_summary=[],
                error_message=None,
                started_at=None,
                completed_at=now,
                created_at=now,
                updated_at=now,
                needs_human=needs_human,
            )
        )
    )


def test_tool_policy_returns_pipeline_payload_without_human_review() -> None:
    projection = _pipeline_projection(needs_human=False)

    assert require_tool_result(projection) is projection.payload


def test_tool_policy_raises_safe_error_for_pipeline_requiring_human_review() -> None:
    projection = _pipeline_projection(needs_human=True)

    with pytest.raises(AgentQueryError) as caught:
        require_tool_result(projection)

    assert caught.value.code == "needs_human"
    assert caught.value.needs_human is True
    assert caught.value.message == (
        "Pipeline execution failed after retries were exhausted; "
        "manual review and check required."
    )


def test_tool_policy_passes_through_other_payload_types() -> None:
    projection = ServiceProjection(payload={"data": [1, 2, 3]})

    assert require_tool_result(projection) is projection.payload
