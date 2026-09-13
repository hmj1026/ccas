"""Pydantic boundary for serialized bill parse results."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TransactionItemSchema(BaseModel):
    """Serialized form of :class:`TransactionItem`."""

    model_config = ConfigDict(extra="forbid")

    trans_date: date
    merchant: str
    amount: int
    posting_date: date | None = None
    currency: str = "TWD"
    original_amount: int | None = None
    card_last4: str | None = None
    installment_current: int | None = None
    installment_total: int | None = None


class BillParseResultSchema(BaseModel):
    """Model-first JSON contract for a normalized bill parse result."""

    model_config = ConfigDict(extra="forbid")

    bank_code: str
    billing_month: str
    total_amount: int
    due_date: date
    transactions: list[TransactionItemSchema]
    due_date_estimated: bool = False
    parse_method: Literal["rules", "ocr", "llm"] = "rules"
    parse_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
