"""Pipeline 進度回報抽象（協定 + 空操作實作）。

原 ``ccas.pipeline.progress`` 的協定面；P3-1 將不依賴 DB 的純結構符號
（``ProgressReporter`` Protocol 與 ``NoopProgressReporter``）下移至 shared
層，讓 stage 模組無需向上依賴 pipeline 即可回報進度。寫入 DB 的
``DbProgressReporter`` 仍留在 ``ccas.pipeline.progress``（依賴 storage 與
pipeline 執行語境）。

設計約束（spec D2 / D3 / D4）：三個 hook 為 async（``stage_started`` /
``stage_item_done`` / ``stage_finished``），底層實作可使用 async DB /
async pubsub 而不阻塞。未來新增 SSE / pubsub reporter 時實作同 Protocol
即可，``run_pipeline`` 與 stage job 簽章不需改動。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

__all__ = ["ProgressReporter", "NoopProgressReporter"]


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
        *,
        counts: Mapping[str, int] | None = None,
        errors: Sequence[str] | None = None,
    ) -> None:
        """通知某階段結束（一律即時 flush，不受節流影響）。

        ``ok`` / ``fail`` 是 UI 列表摘要用的相容欄位；``counts`` /
        ``errors`` 保留原始 ``StageSummary`` 資訊，讓 PipelineRun history
        能作為完整快照。
        """
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
        *,
        counts: Mapping[str, int] | None = None,
        errors: Sequence[str] | None = None,
    ) -> None:
        return None
