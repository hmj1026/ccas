"""Bills Agent query services."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.identity import (
    build_bill_reconciliation_key,
    contains_sensitive_data,
)
from ccas.services.schemas import (
    AgentBill,
    AgentQueryError,
    BillResult,
    BillsPage,
    GetBillInput,
    ListBillsInput,
    Money,
    PageMeta,
    PaymentDueResult,
    ServiceProjection,
)
from ccas.storage.agent_queries import (
    fetch_card_last4s_for_bills,
    get_bill_by_id,
    get_payment_due_query,
    list_bills_query,
)
from ccas.storage.models import Bill
from ccas.storage.queries import fetch_bank_names

MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _to_agent_bill(
    bill: Bill,
    bank_names: dict[str, str],
    card_last4s: list[str],
) -> AgentBill:
    """Validate and convert Bill ORM to AgentBill DTO."""
    if not bill.billing_month or not MONTH_REGEX.match(bill.billing_month):
        raise AgentQueryError(
            "needs_human",
            "Database contains malformed billing month; human review required.",
            needs_human=True,
        )

    bank_name = bank_names.get(bill.bank_code)
    if contains_sensitive_data(bill.bank_code) or contains_sensitive_data(bank_name):
        raise AgentQueryError(
            "needs_human",
            "Bill data contains sensitive information requiring human review.",
            needs_human=True,
        )

    for card in card_last4s:
        if len(card) != 4 or not card.isdigit():
            raise AgentQueryError(
                "needs_human",
                "Database contains malformed card data; human review required.",
                needs_human=True,
            )

    sorted_cards = sorted(set(card_last4s))

    recon_key = build_bill_reconciliation_key(
        bank_code=bill.bank_code,
        billing_month=bill.billing_month,
        card_last4s=sorted_cards,
        due_date=bill.due_date,
    )

    try:
        return AgentBill(
            id=bill.id,
            bank_code=bill.bank_code,
            bank_name=bank_name,
            billing_month=bill.billing_month,
            total_amount=Money(currency="TWD", value=str(int(bill.total_amount))),
            due_date=bill.due_date,
            is_paid=bill.is_paid,
            created_at=bill.created_at,
            card_last4s=sorted_cards,
            reconciliation_key=recon_key,
        )
    except ValidationError as exc:
        raise AgentQueryError(
            "needs_human",
            "Database contains malformed bill data; human review required.",
            needs_human=True,
        ) from exc


async def list_bills(
    session: AsyncSession,
    *,
    month: str | None = None,
    year: int | None = None,
    bank_code: str | None = None,
    status: Literal["all", "paid", "unpaid"] | str = "all",
    page: int = 1,
    page_size: int = 20,
) -> ServiceProjection[BillsPage]:
    """List bills with optional filters, bank names lookup, and pagination."""
    try:
        input_dto = ListBillsInput(
            month=month,
            year=year,
            bank_code=bank_code,
            status=status,  # type: ignore[arg-type]
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise AgentQueryError("invalid_argument", "Invalid argument provided.") from exc

    bank_names = await fetch_bank_names(session)

    bills, total, total_pages, has_next = await list_bills_query(
        session,
        month=input_dto.month,
        year=input_dto.year,
        bank_code=input_dto.bank_code,
        status=input_dto.status,
        page=input_dto.page,
        page_size=input_dto.page_size,
    )

    bill_ids = [b.id for b in bills]
    cards_map = await fetch_card_last4s_for_bills(session, bill_ids)

    rest_metadata: dict[str, Any] = {}
    items: list[AgentBill] = []

    for b in bills:
        cards = cards_map.get(b.id, [])
        items.append(_to_agent_bill(b, bank_names, cards))
        rest_metadata[str(b.id)] = {
            "has_pdf": bool(b.file_path),
            "is_paid": b.is_paid,
        }

    page_meta = PageMeta(
        page=input_dto.page,
        page_size=input_dto.page_size,
        total=total,
        total_pages=total_pages,
        has_next=has_next,
    )

    return ServiceProjection(
        payload=BillsPage(data=items, pagination=page_meta),
        rest_metadata=rest_metadata,
    )


async def get_bill(
    session: AsyncSession,
    bill_id: int,
) -> ServiceProjection[BillResult]:
    """Fetch single bill by ID."""
    try:
        input_dto = GetBillInput(bill_id=bill_id)
    except ValidationError as exc:
        raise AgentQueryError("invalid_argument", "Invalid argument provided.") from exc

    bill = await get_bill_by_id(session, input_dto.bill_id)
    if bill is None:
        raise AgentQueryError("resource_not_found", f"Bill #{bill_id} not found.")

    bank_names = await fetch_bank_names(session)
    cards_map = await fetch_card_last4s_for_bills(session, [bill.id])
    cards = cards_map.get(bill.id, [])

    agent_bill = _to_agent_bill(bill, bank_names, cards)
    rest_metadata: dict[str, Any] = {
        str(bill.id): {
            "has_pdf": bool(bill.file_path),
            "is_paid": bill.is_paid,
        }
    }

    return ServiceProjection(
        payload=BillResult(data=agent_bill),
        rest_metadata=rest_metadata,
    )


async def get_payment_due(
    session: AsyncSession,
) -> ServiceProjection[PaymentDueResult]:
    """Fetch all unpaid bills ordered by due_date ascending."""
    unpaid_bills = await get_payment_due_query(session)
    bank_names = await fetch_bank_names(session)

    bill_ids = [b.id for b in unpaid_bills]
    cards_map = await fetch_card_last4s_for_bills(session, bill_ids)

    items: list[AgentBill] = []
    rest_metadata: dict[str, Any] = {}

    for b in unpaid_bills:
        cards = cards_map.get(b.id, [])
        items.append(_to_agent_bill(b, bank_names, cards))
        rest_metadata[str(b.id)] = {
            "has_pdf": bool(b.file_path),
            "is_paid": b.is_paid,
        }

    return ServiceProjection(
        payload=PaymentDueResult(data=items),
        rest_metadata=rest_metadata,
    )
