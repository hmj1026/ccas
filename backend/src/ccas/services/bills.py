"""Bills Agent query services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
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


class BillRead(BaseModel):
    """Immutable native bill data shared by Agent and REST projections.

    The model contains no storage path. Its ``has_pdf`` flag is only for the
    REST adapter, while ``card_last4s`` is consumed when building the safe
    Agent DTO. Constructing a native read does not run Agent-specific
    month/card validation, which keeps the post-commit PATCH response
    compatible with existing data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    bank_code: str
    bank_name: str | None
    billing_month: str
    total_amount: int
    due_date: date
    is_paid: bool
    created_at: datetime
    has_pdf: bool
    card_last4s: tuple[str, ...] = ()

    @classmethod
    def from_bill(
        cls,
        bill: Bill,
        *,
        bank_name: str | None,
        card_last4s: list[str] | tuple[str, ...] = (),
    ) -> BillRead:
        """Map one ORM bill into native values without Agent-only checks."""
        return cls(
            id=bill.id,
            bank_code=bill.bank_code,
            bank_name=bank_name,
            billing_month=bill.billing_month,
            total_amount=int(bill.total_amount),
            due_date=bill.due_date,
            is_paid=bill.is_paid,
            created_at=bill.created_at,
            has_pdf=bool(bill.file_path),
            card_last4s=tuple(card_last4s),
        )

    def to_agent(self) -> AgentBill:
        """Validate Agent-facing fields and retain the canonical payload."""
        if not self.billing_month or not MONTH_REGEX.match(self.billing_month):
            raise AgentQueryError(
                "needs_human",
                "Database contains malformed billing month; human review required.",
                needs_human=True,
            )

        if contains_sensitive_data(self.bank_code) or contains_sensitive_data(
            self.bank_name
        ):
            raise AgentQueryError(
                "needs_human",
                "Bill data contains sensitive information requiring human review.",
                needs_human=True,
            )

        for card in self.card_last4s:
            if len(card) != 4 or not card.isdigit():
                raise AgentQueryError(
                    "needs_human",
                    "Database contains malformed card data; human review required.",
                    needs_human=True,
                )

        sorted_cards = sorted(set(self.card_last4s))
        recon_key = build_bill_reconciliation_key(
            bank_code=self.bank_code,
            billing_month=self.billing_month,
            card_last4s=sorted_cards,
            due_date=self.due_date,
        )

        try:
            return AgentBill(
                id=self.id,
                bank_code=self.bank_code,
                bank_name=self.bank_name,
                billing_month=self.billing_month,
                total_amount=Money(currency="TWD", value=str(self.total_amount)),
                due_date=self.due_date,
                is_paid=self.is_paid,
                created_at=self.created_at,
                card_last4s=sorted_cards,
                reconciliation_key=recon_key,
            )
        except ValidationError as exc:
            raise AgentQueryError(
                "needs_human",
                "Database contains malformed bill data; human review required.",
                needs_human=True,
            ) from exc


@dataclass(kw_only=True)
class BillProjection[T](ServiceProjection[T]):
    """Safe Agent result and native bill reads from the same query rows."""

    rest_items: tuple[BillRead, ...]


def _bill_read_for_agent(
    bill: Bill,
    bank_name: str | None,
    card_last4s: list[str] | tuple[str, ...],
) -> BillRead:
    """Build a query read while keeping malformed database data safe."""
    try:
        return BillRead.from_bill(
            bill,
            bank_name=bank_name,
            card_last4s=card_last4s,
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
) -> BillProjection[BillsPage]:
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

    bill_ids = [bill.id for bill in bills]
    cards_map = await fetch_card_last4s_for_bills(session, bill_ids)

    native_items = tuple(
        _bill_read_for_agent(
            bill,
            bank_names.get(bill.bank_code),
            cards_map.get(bill.id, []),
        )
        for bill in bills
    )
    items = [bill.to_agent() for bill in native_items]

    page_meta = PageMeta(
        page=input_dto.page,
        page_size=input_dto.page_size,
        total=total,
        total_pages=total_pages,
        has_next=has_next,
    )

    return BillProjection(
        payload=BillsPage(data=items, pagination=page_meta),
        rest_items=native_items,
    )


async def get_bill(
    session: AsyncSession,
    bill_id: int,
) -> BillProjection[BillResult]:
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
    native_bill = _bill_read_for_agent(
        bill,
        bank_names.get(bill.bank_code),
        cards_map.get(bill.id, []),
    )

    return BillProjection(
        payload=BillResult(data=native_bill.to_agent()),
        rest_items=(native_bill,),
    )


async def get_payment_due(
    session: AsyncSession,
) -> BillProjection[PaymentDueResult]:
    """Fetch all unpaid bills ordered by due_date ascending."""
    unpaid_bills = await get_payment_due_query(session)
    bank_names = await fetch_bank_names(session)

    bill_ids = [bill.id for bill in unpaid_bills]
    cards_map = await fetch_card_last4s_for_bills(session, bill_ids)

    native_items = tuple(
        _bill_read_for_agent(
            bill,
            bank_names.get(bill.bank_code),
            cards_map.get(bill.id, []),
        )
        for bill in unpaid_bills
    )
    items = [bill.to_agent() for bill in native_items]

    return BillProjection(
        payload=PaymentDueResult(data=items),
        rest_items=native_items,
    )
