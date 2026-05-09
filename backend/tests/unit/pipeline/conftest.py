"""Shared fixtures for pipeline unit tests.

Centralises the in-memory ``FakeReporter`` used by both
``test_orchestrator_progress_hook.py`` and ``test_stage_progress_hooks.py``.
Hook labels follow the full Protocol method names so callers can match
against the exact contract published by ``ccas.pipeline.progress.ProgressReporter``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class FakeReporter:
    """Captures every ProgressReporter hook invocation in order.

    ``calls`` entries are ``(hook_name, payload_dict)`` tuples where
    ``hook_name`` is one of ``"stage_started" | "stage_item_done" |
    "stage_finished"`` matching the Protocol method names.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def stage_started(self, stage: str, total: int) -> None:
        self.calls.append(("stage_started", {"stage": stage, "total": total}))

    async def stage_item_done(self, stage: str, processed: int) -> None:
        self.calls.append(("stage_item_done", {"stage": stage, "processed": processed}))

    async def stage_finished(
        self,
        stage: str,
        ok: int,
        fail: int,
        elapsed_ms: int,
        *,
        counts: Mapping[str, int] | None = None,
        errors: Sequence[str] | None = None,
    ) -> None:
        self.calls.append(
            (
                "stage_finished",
                {
                    "stage": stage,
                    "ok": ok,
                    "fail": fail,
                    "elapsed_ms": elapsed_ms,
                    "counts": counts or {},
                    "errors": errors or [],
                },
            )
        )


def started_total(reporter: FakeReporter, stage: str) -> int | None:
    """Return the ``total`` reported by the first ``stage_started`` for ``stage``."""
    for kind, payload in reporter.calls:
        if kind == "stage_started" and payload["stage"] == stage:
            return int(payload["total"])
    return None


def items(reporter: FakeReporter, stage: str) -> list[int]:
    """Return ``processed`` values from every ``stage_item_done`` for ``stage``."""
    return [
        int(payload["processed"])
        for kind, payload in reporter.calls
        if kind == "stage_item_done" and payload["stage"] == stage
    ]
