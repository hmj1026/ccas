"""Contract tests for canonical Agent datetime JSON serialization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from ccas.services.schemas import AgentBill, Money, PipelineStatus


def _bill(*, created_at: datetime) -> AgentBill:
    return AgentBill(
        id=1,
        bank_code="CTBC",
        bank_name="中國信託",
        billing_month="2026-04",
        total_amount=Money(currency="TWD", value="1234"),
        due_date=datetime(2026, 5, 15).date(),
        is_paid=False,
        created_at=created_at,
        card_last4s=[],
        reconciliation_key="CTBC:2026-04:due-2026-05-15",
    )


def _pipeline_status(
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    created_at: datetime,
    updated_at: datetime,
) -> PipelineStatus:
    return PipelineStatus(
        id="run-1",
        job_id="job-1",
        status="succeeded",
        triggered_by="test",
        params={"force": False},
        current_stage=None,
        current_stage_processed=0,
        current_stage_total=0,
        stage_summary=[],
        error_message=None,
        started_at=started_at,
        completed_at=completed_at,
        created_at=created_at,
        updated_at=updated_at,
        needs_human=False,
    )


def test_agent_bill_serializes_naive_datetime_as_utc_z() -> None:
    bill = _bill(created_at=datetime(2026, 4, 1, 12, 0, 0, 123456))

    assert bill.model_dump(mode="json")["created_at"] == ("2026-04-01T12:00:00.123456Z")


def test_pipeline_status_converts_non_utc_datetimes_to_utc_z() -> None:
    taipei = timezone(timedelta(hours=8))
    status = _pipeline_status(
        started_at=datetime(2026, 4, 1, 20, 0, 0, tzinfo=taipei),
        completed_at=datetime(2026, 4, 1, 21, 0, 0, tzinfo=taipei),
        created_at=datetime(2026, 4, 1, 19, 0, 0, tzinfo=taipei),
        updated_at=datetime(2026, 4, 1, 22, 0, 0, tzinfo=taipei),
    )

    payload = status.model_dump(mode="json")
    assert payload["started_at"] == "2026-04-01T12:00:00Z"
    assert payload["completed_at"] == "2026-04-01T13:00:00Z"
    assert payload["created_at"] == "2026-04-01T11:00:00Z"
    assert payload["updated_at"] == "2026-04-01T14:00:00Z"


def test_pipeline_status_preserves_nullable_datetime_and_python_mode() -> None:
    status = _pipeline_status(
        started_at=None,
        completed_at=None,
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
    )

    assert status.model_dump(mode="json")["started_at"] is None
    assert status.model_dump(mode="json")["completed_at"] is None
    assert isinstance(status.model_dump(mode="python")["created_at"], datetime)
    assert status.model_dump(mode="json")["params"] == {"force": False}
