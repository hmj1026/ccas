"""Pipeline 進度回報抽象（pipeline-operations-center §2）。

寫入 DB 的 ``DbProgressReporter`` 實作。``ProgressReporter`` Protocol 與
``NoopProgressReporter`` 自 P3-1 起定義於 ``ccas.shared.progress``（解除
stage→pipeline 向上相依），本 module 於頂部 re-export 維持既有 import 路徑。

- :class:`ProgressReporter` / :class:`NoopProgressReporter` — 定義於
  ``ccas.shared.progress``，此處 re-export
- :class:`DbProgressReporter` — RQ worker 路徑使用，將進度寫入
  ``pipeline_runs`` 對應 row（依賴 storage 與 pipeline 執行語境，留在本層）

設計約束（spec D2 / D3 / D4）：

- 三個 hook 為 async：``stage_started``、``stage_item_done``、``stage_finished``
- ``DbProgressReporter`` 對 ``stage_item_done`` 做 250 ms 節流，避免 SQLite
  熱點；``stage_started`` / ``stage_finished`` 一律即時 flush
- 每筆寫入使用獨立 short-lived session（不持有跨 hook 的長活 session），
  避免長活 session 在 SQLite WAL 下持有 read lock
- 階段最後一筆強制 flush（不被節流卡住），由 ``stage_finished`` 同步
  覆寫 ``current_stage_processed = current_stage_total``

未來新增 SSE / pubsub reporter 時實作同 Protocol 即可，``run_pipeline``
與 stage job 簽章不需改動（spec ProgressReporter 升級空間預留）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence

from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.shared.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import PipelineRun

__all__ = ["NoopProgressReporter", "ProgressReporter", "DbProgressReporter"]

#: Type alias for any callable that returns an :class:`AsyncSession` instance.
#: ``async_sessionmaker[AsyncSession]`` from SQLAlchemy satisfies this protocol;
#: tests may inject custom counting / instrumented factories that match the
#: same shape without subclassing ``async_sessionmaker``.
AsyncSessionFactory = Callable[[], AsyncSession]

logger = logging.getLogger(__name__)

THROTTLE_INTERVAL_SECONDS: float = 0.25

#: ``stage_finished`` retry budget for transient ``database is locked``
#: contention (issue #6). The PRAGMA ``busy_timeout=30000`` already gives the
#: kernel-level wait; this loop is a second line of defence for the rare case
#: where the timeout itself elapses (e.g. a long-running batch on the WAL).
_STAGE_FINISHED_MAX_RETRIES: int = 3
_STAGE_FINISHED_BACKOFF_SECONDS: tuple[float, ...] = (0.1, 0.5, 2.0)


# ``ProgressReporter`` Protocol 與 ``NoopProgressReporter`` 已下移至
# ``ccas.shared.progress``（P3-1，解除 stage→pipeline 向上相依），於本模組
# 頂部 re-export 維持相容。``DbProgressReporter`` 因依賴 storage 與 pipeline
# 執行語境，留在 pipeline 層。


class DbProgressReporter:
    """將進度寫入 ``pipeline_runs.id=run_id`` row 的 reporter。

    每筆 hook 觸發時開啟一個獨立 short-lived async session、執行單一
    ``UPDATE pipeline_runs SET ... WHERE id=?``、立即 commit 後關閉。
    ``stage_item_done`` 對同 reporter 實例做 250 ms 節流（``asyncio.Lock``
    保護 ``_last_flush_at``），同階段最後一筆由後續 ``stage_finished`` 強制
    覆寫，確保「99/100 顯示」不會被吞。

    SQLite trigger 已確保 ``updated_at`` 在 Core-style UPDATE 下自動刷新
    （見 alembic ``0a2c400f1179``），本實作無需顯式設 ``updated_at``。
    """

    def __init__(
        self,
        run_id: str,
        session_factory: AsyncSessionFactory,
        *,
        throttle_seconds: float = THROTTLE_INTERVAL_SECONDS,
    ) -> None:
        self._run_id = run_id
        self._session_factory = session_factory
        self._throttle_seconds = throttle_seconds
        self._lock = asyncio.Lock()
        self._last_flush_at: float = 0.0

    async def stage_started(self, stage: str, total: int) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == self._run_id)
                .values(
                    current_stage=stage,
                    current_stage_processed=0,
                    current_stage_total=total,
                )
            )
            await session.commit()
        # Reset throttle window so first item_done fires immediately for new
        # stage; otherwise the prior stage's last flush could suppress it.
        async with self._lock:
            self._last_flush_at = 0.0

    async def stage_item_done(self, stage: str, processed: int) -> None:
        async with self._lock:
            now = time.monotonic()
            if now - self._last_flush_at < self._throttle_seconds:
                return
            self._last_flush_at = now

        async with self._session_factory() as session:
            await session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == self._run_id)
                .values(
                    current_stage=stage,
                    current_stage_processed=processed,
                )
            )
            await session.commit()

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
        """Atomically append a stage summary entry and overwrite progress.

        Issue #6: retries transient ``database is locked`` errors using
        ``asyncio.sleep`` for backoff — must therefore be invoked from an
        async context (the worker pipeline already runs each job under
        ``asyncio.run`` per RQ task; sync callers would deadlock).
        """
        # stage_finished MUST bypass throttle and atomically:
        #   1. Append stage summary JSON, including rich counts/errors
        #   2. Overwrite current_stage_processed = current_stage_total
        # Read-then-write inside one session; PipelineRun rows are written
        # only by the worker holding this reporter, so race is impossible
        # for a single run. Each retry opens a fresh session, so the prior
        # failed-commit transaction is implicitly rolled back and re-reading
        # ``stage_summary`` cannot observe a partial append.
        entry = {
            "stage": stage,
            "ok": int(ok),
            "fail": int(fail),
            "elapsed_ms": int(elapsed_ms),
            "counts": {str(name): int(count) for name, count in (counts or {}).items()},
            "errors": [str(error) for error in (errors or [])],
        }

        last_exc: OperationalError | None = None
        for attempt in range(_STAGE_FINISHED_MAX_RETRIES):
            try:
                async with self._session_factory() as session:
                    row = await session.get(PipelineRun, self._run_id)
                    if row is None:
                        logger.warning(
                            "pipeline_runs row %s not found",
                            self._run_id,
                            extra={"run_id": self._run_id, "stage": stage},
                        )
                        return
                    new_summary = list(row.stage_summary or []) + [entry]
                    row.stage_summary = new_summary
                    row.current_stage_processed = row.current_stage_total
                    await session.commit()
                break
            except OperationalError as exc:
                # SQLite raises ``sqlite3.OperationalError("database is
                # locked")`` for SQLITE_BUSY; CPython does not expose a
                # numeric code, so substring match on ``exc.args[0]`` is the
                # standard recovery hook (see SQLAlchemy issue #5184).
                message = exc.args[0] if exc.args else ""
                if "database is locked" not in str(message):
                    raise
                last_exc = exc
                if attempt + 1 >= _STAGE_FINISHED_MAX_RETRIES:
                    logger.error(
                        "stage_finished gave up after retries on database-locked",
                        extra={
                            "run_id": self._run_id,
                            "stage": stage,
                            "attempts": _STAGE_FINISHED_MAX_RETRIES,
                        },
                    )
                    raise
                backoff = _STAGE_FINISHED_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "stage_finished hit database-locked; retrying",
                    extra={
                        "run_id": self._run_id,
                        "stage": stage,
                        "attempt": attempt + 1,
                        "max_attempts": _STAGE_FINISHED_MAX_RETRIES,
                        "backoff_s": backoff,
                    },
                )
                await asyncio.sleep(backoff)
        else:  # pragma: no cover — loop always breaks or raises
            raise RuntimeError(
                "stage_finished retry loop exited without break or raise"
            ) from last_exc

        async with self._lock:
            self._last_flush_at = time.monotonic()
