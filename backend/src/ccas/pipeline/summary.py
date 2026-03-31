"""Pipeline 摘要結構定義。

PipelineSummary 作為 CLI 輸出與 RQ job result 的共同格式。
"""

from dataclasses import dataclass, field


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
