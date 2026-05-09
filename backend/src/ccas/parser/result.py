"""ParseResult 資料結構。

定義 parser 輸出的正規化帳單與交易明細格式，
不直接耦合 ORM model，由 orchestrator 負責持久化。
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TransactionItem:
    """單筆交易明細。

    Attributes:
        trans_date: 交易日期。
        merchant: 商家名稱。
        amount: 金額（整數，元為單位）。
        posting_date: 入帳日期（可為 None）。
        currency: 幣別，預設 "TWD"。
        original_amount: 外幣原始金額（可為 None）。
        card_last4: 卡號末四碼（可為 None）。
        installment_current: 目前期數（可為 None）。
        installment_total: 總期數（可為 None）。
    """

    trans_date: date
    merchant: str
    amount: int
    posting_date: date | None = None
    currency: str = "TWD"
    original_amount: int | None = None
    card_last4: str | None = None
    installment_current: int | None = None
    installment_total: int | None = None


@dataclass(frozen=True)
class ParseResult:
    """Parser 解析結果。

    承載正規化的帳單摘要與交易明細列表，
    不直接耦合 ORM model。

    Attributes:
        bank_code: 銀行代碼。
        billing_month: 帳單月份（格式如 "2026-03"）。
        total_amount: 應繳總額（整數，元為單位）。
        due_date: 繳費截止日。
        transactions: 交易明細列表（tuple，不可變）。
    """

    bank_code: str
    billing_month: str
    total_amount: int
    due_date: date
    transactions: tuple[TransactionItem, ...]
