"""CCAS 共用例外定義。

所有模組例外均繼承 CcasError 基底類別，確保跨模組錯誤可被統一捕捉。
錯誤訊息格式：[ModuleName] <描述>: <原因>
"""

from __future__ import annotations

from typing import Any


class CcasError(Exception):
    """CCAS 所有可恢復錯誤的基底例外。

    用於 pipeline 執行異常，供 RQ job 重試邏輯捕捉。

    Attributes:
        message: 人類可讀的錯誤描述。
        context: 可選的結構化診斷資訊（例如附件路徑、銀行代碼）。
    """

    def __init__(
        self, message: str = "", *, context: dict[str, Any] | None = None
    ) -> None:
        self.message = message
        self.context = context or {}
        super().__init__(message)


def _fmt(module: str, description: str, reason: str) -> str:
    if reason:
        return f"[{module}] {description}: {reason}"
    return f"[{module}] {description}"


class IngestError(CcasError):
    """Gmail 抓取 / 附件 staging 階段的錯誤。"""

    def __init__(self, description: str, reason: str = "", **ctx: Any) -> None:
        super().__init__(_fmt("Ingest", description, reason), context=ctx)


class DecryptError(CcasError):
    """PDF 解密階段的錯誤。"""

    def __init__(self, description: str, reason: str = "", **ctx: Any) -> None:
        super().__init__(_fmt("Decrypt", description, reason), context=ctx)


class ParseError(CcasError):
    """PDF 解析階段的錯誤。"""

    def __init__(self, description: str, reason: str = "", **ctx: Any) -> None:
        super().__init__(_fmt("Parse", description, reason), context=ctx)


class ClassifyError(CcasError):
    """交易分類階段的錯誤。"""

    def __init__(self, description: str, reason: str = "", **ctx: Any) -> None:
        super().__init__(_fmt("Classify", description, reason), context=ctx)


class NotifyError(CcasError):
    """Telegram 通知發送階段的錯誤。"""

    def __init__(self, description: str, reason: str = "", **ctx: Any) -> None:
        super().__init__(_fmt("Notify", description, reason), context=ctx)
