"""ParseResult 資料結構。

定義 parser 輸出的正規化帳單與交易明細格式，
不直接耦合 ORM model，由 orchestrator 負責持久化。
"""

import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

ParseMethod = Literal["rules", "ocr", "llm"]
PARSE_CONFIDENCE_THRESHOLD = 0.85
_CONFIDENCE_QUANTUM = Decimal("0.01")
_BILLING_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_CARD_LAST4_RE = re.compile(r"^\d{4}$")


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
        due_date_estimated: 內部觀測旗標。為 ``True`` 時表示 ``due_date``
            為估算值（非帳單明載），目前僅 CTBC 兩頁帳單在缺乏精確截止日時
            退而估算為當月 28 日的路徑會設為 ``True``。此旗標**不**對外暴露於
            任何 API/前端 schema，僅供持久化、可觀測性與提醒邏輯使用。
        parse_method: 產生此結果的路徑（rules、ocr 或 llm）。
        parse_confidence: 0.0～1.0 的可重現解析信心分數。
        needs_review: 是否需要人工審查。
        review_reasons: 觸發人工審查的可讀原因。
    """

    bank_code: str
    billing_month: str
    total_amount: int
    due_date: date
    transactions: tuple[TransactionItem, ...]
    due_date_estimated: bool = False
    parse_method: ParseMethod = "rules"
    parse_confidence: float = 1.0
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseAssessment:
    """解析結果的可重現品質評估。"""

    field_score: float
    check_score: float
    parse_confidence: float
    needs_review: bool
    review_reasons: tuple[str, ...]


def _is_valid_billing_month(value: object) -> bool:
    if not isinstance(value, str):
        return False
    match = _BILLING_MONTH_RE.fullmatch(value)
    if match is None:
        return False
    return 1 <= int(match.group(2)) <= 12


def _field_validity(result: ParseResult) -> tuple[bool, bool, bool, bool]:
    """Return validity for bank, month, amount and due date in that order."""
    return (
        isinstance(result.bank_code, str) and bool(result.bank_code.strip()),
        _is_valid_billing_month(result.billing_month),
        isinstance(result.total_amount, int) and result.total_amount >= 0,
        isinstance(result.due_date, date) and result.due_date > date.min,
    )


def _applicable_checks(result: ParseResult) -> tuple[int, int, tuple[str, ...]]:
    """Return passed checks, total checks and human-readable failures."""
    passed = 0
    total = 0
    reasons: list[str] = []

    if result.transactions:
        total += 1
        if sum(item.amount for item in result.transactions) == result.total_amount:
            passed += 1
        else:
            reasons.append("交易明細加總與帳單總額不一致")

        total += 1
        if all(item.trans_date <= result.due_date for item in result.transactions):
            passed += 1
        else:
            reasons.append("交易日期超過繳費截止日")

        card_values = [
            item.card_last4 for item in result.transactions if item.card_last4
        ]
        if card_values:
            total += 1
            if all(_CARD_LAST4_RE.fullmatch(value) for value in card_values):
                passed += 1
            else:
                reasons.append("卡號末四碼格式不正確")

    return passed, total, tuple(reasons)


def assess_parse_result(result: ParseResult) -> ParseAssessment:
    """Calculate the fixed confidence gate for a parse candidate.

    The score is ``round_half_up(0.7 * field_score + 0.3 * check_score, 2)``.
    The function does not mutate or reinterpret the parser path; callers can
    use :func:`finalize_parse_result` when a fallback candidate is ready.
    """
    fields = _field_validity(result)
    field_score = Decimal(sum(fields)) / Decimal(4)
    passed_checks, total_checks, check_reasons = _applicable_checks(result)
    check_score = (
        Decimal(passed_checks) / Decimal(total_checks) if total_checks else Decimal(1)
    )
    confidence = (Decimal("0.7") * field_score + Decimal("0.3") * check_score).quantize(
        _CONFIDENCE_QUANTUM, rounding=ROUND_HALF_UP
    )

    reasons = list(check_reasons)
    field_names = ("bank_code", "billing_month", "total_amount", "due_date")
    reasons.extend(
        f"必要欄位 {name} 無效"
        for name, is_valid in zip(field_names, fields, strict=True)
        if not is_valid
    )
    if confidence < Decimal(str(PARSE_CONFIDENCE_THRESHOLD)):
        reasons.append(
            f"解析信心 {confidence:.2f} 低於門檻 {PARSE_CONFIDENCE_THRESHOLD:.2f}"
        )

    return ParseAssessment(
        field_score=float(field_score),
        check_score=float(check_score),
        parse_confidence=float(confidence),
        needs_review=bool(reasons),
        review_reasons=tuple(dict.fromkeys(reasons)),
    )


def finalize_parse_result(
    result: ParseResult,
    *,
    method: ParseMethod,
) -> ParseResult:
    """Attach deterministic metadata to a rules/OCR/LLM candidate."""
    assessment = assess_parse_result(result)
    return replace(
        result,
        parse_method=method,
        parse_confidence=assessment.parse_confidence,
        needs_review=assessment.needs_review,
        review_reasons=assessment.review_reasons,
    )


def is_parse_result_acceptable(result: ParseResult) -> bool:
    """Return whether a candidate may become formal bill data."""
    return (
        0.0 <= result.parse_confidence <= 1.0
        and result.parse_confidence >= PARSE_CONFIDENCE_THRESHOLD
        and result.needs_review is False
        and not result.review_reasons
    )
