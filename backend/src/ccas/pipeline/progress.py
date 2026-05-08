"""Pipeline 進度回報抽象（pipeline-operations-center §2）。

提供 ``ProgressReporter`` Protocol，由 orchestrator / stage job 在不感知具體
寫入媒介的前提下回報執行進度。本 module 內含兩個實作：

- :class:`NoopProgressReporter` — CLI / scheduler 路徑使用，所有 hook 為空操作
- :class:`DbProgressReporter` — RQ worker 路徑使用，將進度寫入
  ``pipeline_runs`` 對應 row

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
from collections.abc import Callable
from typing import Protocol

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import PipelineRun

#: Type alias for any callable that returns an :class:`AsyncSession` instance.
#: ``async_sessionmaker[AsyncSession]`` from SQLAlchemy satisfies this protocol;
#: tests may inject custom counting / instrumented factories that match the
#: same shape without subclassing ``async_sessionmaker``.
AsyncSessionFactory = Callable[[], AsyncSession]

logger = logging.getLogger(__name__)

THROTTLE_INTERVAL_SECONDS: float = 0.25


class ProgressReporter(Protocol):
    """Pipeline 進度回報介面。

    所有方法皆為 async，以便底層實作可使用 async DB / async pubsub 而不阻塞。
    Protocol 不強制實作的 reporter 繼承本類別（structural typing）。
    """

    async def stage_started(self, stage: str, total: int) -> None:
        """通知某階段開始，附上預期處理 item 總數。"""
        ...

    async def stage_item_done(self, stage: str, processed: int) -> None:
        """通知某階段完成第 N 個 item（高頻、可被節流）。"""
        ...

    async def stage_finished(
        self,
        stage: str,
        ok: int,
        fail: int,
        elapsed_ms: int,
    ) -> None:
        """通知某階段結束（一律即時 flush，不受節流影響）。"""
        ...


class NoopProgressReporter:
    """空操作 reporter（CLI / scheduler 預設）。

    所有 hook 不對外產生副作用；將 ``run_pipeline`` 的 ``progress_reporter``
    參數預設為 None 時，``run_pipeline`` 內部 SHALL 自動包成本類別實例，
    以便 stage job 可無條件呼叫 hook。
    """

    async def stage_started(self, stage: str, total: int) -> None:
        return None

    async def stage_item_done(self, stage: str, processed: int) -> None:
        return None

    async def stage_finished(
        self,
        stage: str,
        ok: int,
        fail: int,
        elapsed_ms: int,
    ) -> None:
        return None


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
    ) -> None:
        # stage_finished MUST bypass throttle and atomically:
        #   1. Append {stage, ok, fail, elapsed_ms} to stage_summary JSON
        #   2. Overwrite current_stage_processed = current_stage_total
        # Read-then-write inside one session; PipelineRun rows are written
        # only by the worker holding this reporter, so race is impossible
        # for a single run.
        async with self._session_factory() as session:
            row = await session.get(PipelineRun, self._run_id)
            if row is None:
                logger.warning(
                    "DbProgressReporter: pipeline_runs row %s not found",
                    self._run_id,
                )
                return
            entry = {
                "stage": stage,
                "ok": int(ok),
                "fail": int(fail),
                "elapsed_ms": int(elapsed_ms),
            }
            new_summary = list(row.stage_summary or []) + [entry]
            row.stage_summary = new_summary
            row.current_stage_processed = row.current_stage_total
            await session.commit()

        async with self._lock:
            self._last_flush_at = time.monotonic()
