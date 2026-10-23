"""Transactions Agent query services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.identity import (
    build_transaction_reconciliation_key,
    contains_sensitive_data,
)
from ccas.services.schemas import (
    AgentQueryError,
    AgentTransaction,
    Money,
    PageMeta,
    QueryTransactionsInput,
    ServiceProjection,
    TransactionsPage,
)
from ccas.storage.agent_queries import query_transactions_query

MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class TransactionRead(BaseModel):
    """Complete native transaction read, before transport-specific money encoding.

    Currency travels with its transaction; no adapter has to join an auxiliary
    metadata dictionary or infer a missing currency. This is internal data,
    never the public Agent payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    bill_id: int
    trans_date: date
    posting_date: date | None
    merchant: str
    amount: int
    currency: str
    original_amount: int | None
    card_last4: str | None
    category: str | None
    bank_code: str
    billing_month: str
    installment_current: int | None
    installment_total: int | None
    reconciliation_key: str

    def to_agent(self) -> AgentTransaction:
        """Preserve the existing Agent TWD contract, independently of REST currency."""
        return AgentTransaction(
            **self.model_dump(exclude={"amount", "currency", "original_amount"}),
            amount=Money(currency="TWD", value=str(self.amount)),
            original_amount=(
                Money(currency="TWD", value=str(self.original_amount))
                if self.original_amount is not None
                else None
            ),
        )


@dataclass(kw_only=True)
class TransactionProjection(ServiceProjection[TransactionsPage]):
    """Safe Agent payload and complete, typed native reads from the same rows.

    The inherited rest_metadata remains empty for generic caller compatibility;
    transaction adapters consume rest_items exclusively.
    """

    rest_items: tuple[TransactionRead, ...]


async def query_transactions(
    session: AsyncSession,
    *,
    month: str | None = None,
    year: int | None = None,
    bank_code: str | None = None,
    category: str | None = None,
    q: str | None = None,
    sort: Literal[
        "trans_date_asc",
        "trans_date_desc",
        "amount_asc",
        "amount_desc",
        "merchant_asc",
        "merchant_desc",
    ]
    | str = "trans_date_desc",
    page: int = 1,
    page_size: int = 20,
) -> TransactionProjection:
    """Query transactions with filtering, sorting, duplicate ordinals,
    and pagination.
    """
    try:
        input_dto = QueryTransactionsInput(
            month=month,
            year=year,
            bank_code=bank_code,
            category=category,
            q=q,
            sort=sort,  # type: ignore[arg-type]
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise AgentQueryError("invalid_argument", "Invalid argument provided.") from exc

    rows, total, total_pages, has_next = await query_transactions_query(
        session,
        month=input_dto.month,
        year=input_dto.year,
        bank_code=input_dto.bank_code,
        category=input_dto.category,
        q=input_dto.q,
        sort=input_dto.sort,
        page=input_dto.page,
        page_size=input_dto.page_size,
    )

    items: list[AgentTransaction] = []
    rest_items: list[TransactionRead] = []

    for row in rows:
        if not row.bill_billing_month or not MONTH_REGEX.match(row.bill_billing_month):
            raise AgentQueryError(
                "needs_human",
                "Database contains malformed billing month; human review required.",
                needs_human=True,
            )

        card_last4 = row.card_last4
        if card_last4 == "":
            card_last4 = None
        elif card_last4 is not None:
            card_str = str(card_last4)
            if len(card_str) != 4 or not card_str.isdigit():
                raise AgentQueryError(
                    "needs_human",
                    "Database contains malformed card data; human review required.",
                    needs_human=True,
                )
            card_last4 = card_str

        if (
            contains_sensitive_data(row.merchant)
            or contains_sensitive_data(row.category)
            or contains_sensitive_data(row.bill_bank_code)
        ):
            raise AgentQueryError(
                "needs_human",
                "Transaction contains sensitive information requiring human review.",
                needs_human=True,
            )

        recon_key = build_transaction_reconciliation_key(
            bill_id=row.bill_id,
            trans_date=row.trans_date,
            amount=row.amount,
            merchant=row.merchant,
            dup_ordinal=row.dup_ordinal,
        )

        try:
            native = TransactionRead(
                id=row.id,
                bill_id=row.bill_id,
                trans_date=row.trans_date,
                posting_date=row.posting_date,
                merchant=row.merchant,
                amount=int(row.amount),
                currency=row.currency,
                original_amount=(
                    int(row.original_amount)
                    if row.original_amount is not None
                    else None
                ),
                card_last4=card_last4,
                category=row.category,
                bank_code=row.bill_bank_code,
                billing_month=row.bill_billing_month,
                installment_current=row.installment_current,
                installment_total=row.installment_total,
                reconciliation_key=recon_key,
            )
            item = native.to_agent()
        except ValidationError as exc:
            raise AgentQueryError(
                "needs_human",
                "Database contains malformed transaction data; human review required.",
                needs_human=True,
            ) from exc

        items.append(item)
        rest_items.append(native)

    page_meta = PageMeta(
        page=input_dto.page,
        page_size=input_dto.page_size,
        total=total,
        total_pages=total_pages,
        has_next=has_next,
    )

    return TransactionProjection(
        payload=TransactionsPage(data=items, pagination=page_meta),
        rest_items=tuple(rest_items),
    )
