"""Pipeline run 結果的單一權威來源（single outcome authority）。

集中三件曾散落於 ``orchestrator.py`` / ``worker.py`` 的職責：

- 將單一階段摘要換算為 ``ProgressReporter.stage_finished`` 需要的 (ok, fail)
- 判定整個 run 應標記 SUCCEEDED 或 FAILED（含 classify 整批 rollback 偵測）
- 將判定結果持久化至 ``pipeline_runs``（``LifecycleStore`` Protocol 抽象，
  ``DbLifecycleStore`` 為 RQ worker 路徑實作，``InMemoryLifecycleStore`` 供測試）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.pipeline.summary import PipelineSummary, StageSummary
from ccas.storage.models import (
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
)

#: Type alias for any callable that returns an :class:`AsyncSession` instance.
AsyncSessionFactory = Callable[[], AsyncSession]


@dataclass(frozen=True)
class StageProgress:
    """單一階段的 (ok, fail) 進度計數。"""

    stage: str
    ok: int
    fail: int


@dataclass(frozen=True)
class LifecycleResult:
    """一次 run 的終態判定結果。"""

    status: PipelineRunStatus
    error_message: str | None
    stage_progress: tuple[StageProgress, ...] = ()
    terminal_reason: PipelineRunTerminalReason | None = None

    @classmethod
    def failed(
        cls,
        msg: str,
        *,
        terminal_reason: (
            PipelineRunTerminalReason
        ) = PipelineRunTerminalReason.WORKER_EXCEPTION,
    ) -> LifecycleResult:
        """建立一個 FAILED 結果（例如 run_pipeline 拋出未預期例外時）。"""
        return cls(
            status=PipelineRunStatus.FAILED,
            error_message=msg,
            terminal_reason=terminal_reason,
        )


@runtime_checkable
class LifecycleStore(Protocol):
    """Pipeline run 生命週期持久化介面。"""

    async def persist_progress(self, run_id: str) -> None:
        """將 run 標記為進行中（QUEUED -> RUNNING，記錄 started_at）。"""
        ...

    async def persist_terminal(self, run_id: str, result: LifecycleResult) -> None:
        """將 run 標記為終態（SUCCEEDED / FAILED），記錄 completed_at。"""
        ...


class RunLifecycle:
    """Pipeline run 結果判定的單一權威。"""

    @staticmethod
    def stage_progress(stage_summary: StageSummary) -> tuple[int, int]:
        """Derive (ok, fail) counts for ProgressReporter.stage_finished.

        ``fail`` maps directly to the ``failed`` bucket in stage counts.
        ``ok`` aggregates everything else (staged / decrypted / passthrough /
        parsed / skipped / classified / sent) since they all represent items
        that progressed without error from the stage's perspective.
        """
        counts = stage_summary.counts
        fail = counts.get("failed", 0)
        ok = sum(counts.values()) - fail
        return ok, fail

    @staticmethod
    def _classify_batch_failed(summary: PipelineSummary) -> bool:
        """偵測 classify 階段是否整批 commit 失敗。

        classify 是 all-or-nothing：``_flush_commit_or_rollback`` 失敗時會 rollback
        整批並拋 ``ClassifyError``，但 ``orchestrator._run_stage`` 將其捕捉成
        ``StageSummary(counts={"failed": 1})`` 後 ``run_pipeline`` 仍正常回傳。
        若不偵測，worker 會誤呼叫 ``mark_pipeline_run_succeeded``，導致分類結果已
        全數 rollback 卻標記成功。成功路徑的 classify 摘要為
        ``counts={"classified": N}``（無 ``failed`` 鍵），因此以 ``failed > 0``
        作為整批失敗的判定訊號。
        """
        for stage in summary.stages:
            if stage.stage == "classify" and stage.counts.get("failed", 0) > 0:
                return True
        return False

    @staticmethod
    def failure_reason(summary: PipelineSummary) -> str | None:
        """回傳應將 run 標記為 FAILED 的原因字串，否則 None（成功）。

        兩類失敗訊號：
        - classify 整批 rollback：以 ``counts['failed']`` 表示（無 errors），
          由 ``_classify_batch_failed`` 偵測，優先回傳明確訊息。
        - 其他階段（ingest/decrypt/parse/notify）的錯誤：以 stage.errors 記錄並
          聚合進 ``summary.failures``。此前 worker 只看 classify counts，使得
          Gmail 分頁中途失敗等情形 failed_count 維持 0 卻仍被標 SUCCEEDED，
          N 封郵件靜默遺漏。改為只要有任一階段失敗即標 FAILED（對齊 CLI 以
          ``summary.failures`` 非空 exit 1 的語意）。
        """
        if RunLifecycle._classify_batch_failed(summary):
            return "classify 階段整批 commit 失敗，分類結果已 rollback"
        # 直接掃資料階段 errors（不依賴 orchestrator 是否已聚合進 summary.failures），
        # 涵蓋 ingest 分頁中途失敗等「counts.failed=0 但有錯誤字串」的靜默資料遺漏。
        # 排除 ``notify``：通知為盡力而為通道（Telegram 單筆逾時等），帳單資料此時
        # 已完整持久化，且 notify 自身以 PaymentReminder 唯一鍵冪等重試——單筆通知
        # 失敗不應讓整個 run 在儀表板顯示 FAILED（誤導操作員以為資料管線壞了）。
        stage_errors = [
            (stage.stage, err)
            for stage in summary.stages
            if stage.stage != "notify"
            for err in stage.errors
        ]
        if stage_errors:
            first_stage, first_err = stage_errors[0]
            return (
                f"pipeline 有 {len(stage_errors)} 項階段失敗"
                f"（首例 {first_stage}：{first_err}）"
            )
        return None

    @classmethod
    def classify(cls, summary: PipelineSummary) -> LifecycleResult:
        """判定整個 run 的終態結果（SUCCEEDED / FAILED）。"""
        reason = cls.failure_reason(summary)
        stage_progress = tuple(
            StageProgress(stage=ss.stage, ok=ok, fail=fail)
            for ss in summary.stages
            for ok, fail in (cls.stage_progress(ss),)
        )
        if reason is not None:
            return LifecycleResult(
                status=PipelineRunStatus.FAILED,
                error_message=reason,
                stage_progress=stage_progress,
                terminal_reason=PipelineRunTerminalReason.STAGE_FAILURE,
            )
        return LifecycleResult(
            status=PipelineRunStatus.SUCCEEDED,
            error_message=None,
            stage_progress=stage_progress,
            terminal_reason=PipelineRunTerminalReason.SUCCEEDED,
        )


@dataclass
class InMemoryLifecycleStore:
    """測試用的記憶體內 :class:`LifecycleStore` 實作。"""

    progress_started: list[str] = field(default_factory=list)
    terminals: dict[str, LifecycleResult] = field(default_factory=dict)

    async def persist_progress(self, run_id: str) -> None:
        self.progress_started.append(run_id)

    async def persist_terminal(self, run_id: str, result: LifecycleResult) -> None:
        self.terminals[run_id] = result


_UNSET = object()


class DbLifecycleStore:
    """將 run 生命週期寫入 ``pipeline_runs`` 的 :class:`LifecycleStore` 實作。

    每次呼叫開啟一個獨立 short-lived session（不持有跨呼叫的長活 session）。
    """

    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory

    async def persist_progress(self, run_id: str) -> None:
        async with self._session_factory() as session:
            await self._set_pipeline_run_status(
                session,
                run_id,
                PipelineRunStatus.RUNNING,
                started_at=datetime.now(UTC),
                completed_at=None,
                error_message=None,
                terminal_reason=None,
            )

    async def persist_terminal(self, run_id: str, result: LifecycleResult) -> None:
        async with self._session_factory() as session:
            await self._set_pipeline_run_status(
                session,
                run_id,
                result.status,
                completed_at=datetime.now(UTC),
                error_message=result.error_message,
                terminal_reason=result.terminal_reason,
            )

    @staticmethod
    async def _set_pipeline_run_status(
        session: AsyncSession,
        run_id: str,
        status: PipelineRunStatus,
        *,
        started_at: datetime | None | object = _UNSET,
        completed_at: datetime | None | object = _UNSET,
        error_message: str | None | object = _UNSET,
        terminal_reason: PipelineRunTerminalReason | None | object = _UNSET,
    ) -> None:
        """寫入 PipelineRun 狀態與對應時間戳 / 原因欄位。

        僅設置呼叫端顯式傳入的欄位（未傳入的 _UNSET 不寫入），避免在
        running → failed / succeeded 轉換時誤覆寫 started_at；
        顯式傳入 None 時則會清除該欄位（例如 persist_progress 重試時清除前次終態）。
        """
        values: dict[str, object] = {"status": status}
        if started_at is not _UNSET:
            values["started_at"] = started_at
        if completed_at is not _UNSET:
            values["completed_at"] = completed_at
        if error_message is not _UNSET:
            values["error_message"] = error_message
        if terminal_reason is not _UNSET:
            values["terminal_reason"] = terminal_reason

        await session.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(**values)
        )
        await session.commit()
