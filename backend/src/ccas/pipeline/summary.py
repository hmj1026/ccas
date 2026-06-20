"""Pipeline 摘要結構定義。

PipelineSummary 作為 CLI 輸出與 RQ job result 的共同格式。
"""

from dataclasses import dataclass, field


@dataclass
class NotifySummary:
    """通知階段的統計摘要。

    放在 pipeline 層（而非 bot 層）以解除 ``pipeline.orchestrator`` 對 ``bot``
    的反向相依：orchestrator 僅需此結構定義，不需 import bot。``bot.job`` 仍
    re-export 此名稱以維持既有 import 路徑。

    Attributes:
        sent_count: 成功發送的通知數。
        failed_count: 發送失敗的數量。
        errors: 錯誤訊息清單。
    """

    sent_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FailedItem:
    """單一失敗項目的 ID 與錯誤訊息。"""

    item_id: str
    error: str


@dataclass(frozen=True)
class StageSummary:
    """單一階段的統計。"""

    stage: str
    counts: dict[str, int]
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineSummary:
    """Pipeline 完整執行摘要。

    Attributes:
        stages: 各階段統計清單。
        total_seconds: Pipeline 總耗時秒數。
        failures: 失敗項目清單（含 ID 與錯誤訊息）。
    """

    stages: tuple[StageSummary, ...]
    total_seconds: float
    failures: tuple[FailedItem, ...] = ()
