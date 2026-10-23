"""Public transaction query and REST projection compatibility tests."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.schemas import AgentQueryError
from ccas.services.transactions import query_transactions
from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers

_PRIVATE_NOTE = "token=rest-projection-test-secret"
_PAN = "4111111111111111"


async def _seed_projection_cases(
    session: AsyncSession,
) -> tuple[Transaction, Transaction, Transaction]:
    session.add(
        BankConfig(
            bank_code="CTBC",
            bank_name="CTBC",
            gmail_filter="from:ctbc",
        )
    )
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=-73,
        due_date=date(2026, 4, 15),
    )
    session.add(bill)
    await session.flush()

    foreign_refund = Transaction(
        bill_id=bill.id,
        trans_date=date(2026, 3, 10),
        merchant="Foreign refund",
        amount=-123,
        currency="USD",
        original_amount=-10,
        note=_PRIVATE_NOTE,
    )
    zero_amount = Transaction(
        bill_id=bill.id,
        trans_date=date(2026, 3, 11),
        merchant="Zero amount purchase",
        amount=0,
        currency="JPY",
        original_amount=0,
    )
    nullable_original = Transaction(
        bill_id=bill.id,
        trans_date=date(2026, 3, 12),
        merchant="Local purchase",
        amount=50,
        currency="TWD",
        original_amount=None,
    )
    session.add_all([foreign_refund, zero_amount, nullable_original])
    await session.commit()
    return foreign_refund, zero_amount, nullable_original


async def test_agent_and_rest_transaction_projections_preserve_money_and_pages(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    foreign_refund, zero_amount, nullable_original = await _seed_projection_cases(
        db_session
    )

    agent_page_one = await query_transactions(
        db_session,
        month="2026-03",
        sort="amount_asc",
        page=1,
        page_size=2,
    )
    assert [item.id for item in agent_page_one.payload.data] == [
        foreign_refund.id,
        zero_amount.id,
    ]
    assert agent_page_one.payload.data[0].amount.model_dump() == {
        "currency": "TWD",
        "value": "-123",
    }
    assert agent_page_one.payload.data[0].original_amount is not None
    assert agent_page_one.payload.data[0].original_amount.model_dump() == {
        "currency": "TWD",
        "value": "-10",
    }
    assert agent_page_one.payload.data[1].original_amount is not None
    assert agent_page_one.payload.data[1].original_amount.model_dump() == {
        "currency": "TWD",
        "value": "0",
    }
    assert agent_page_one.payload.pagination.model_dump() == {
        "page": 1,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
        "has_next": True,
    }
    assert "currency" not in agent_page_one.payload.data[0].model_dump()
    assert "note" not in agent_page_one.payload.data[0].model_dump()
    assert _PRIVATE_NOTE not in agent_page_one.payload.model_dump_json()

    agent_page_two = await query_transactions(
        db_session,
        month="2026-03",
        sort="amount_asc",
        page=2,
        page_size=2,
    )
    assert [item.id for item in agent_page_two.payload.data] == [nullable_original.id]
    assert agent_page_two.payload.data[0].original_amount is None
    assert agent_page_two.payload.pagination.has_next is False

    response = await client.get(
        "/api/transactions?month=2026-03&sort=amount_asc&page=1&page_size=2",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["data"]] == [
        foreign_refund.id,
        zero_amount.id,
    ]
    assert body["data"][0]["amount"] == -123
    assert body["data"][0]["currency"] == "USD"
    assert body["data"][0]["original_amount"] == -10
    assert body["data"][1]["amount"] == 0
    assert body["data"][1]["currency"] == "JPY"
    assert body["data"][1]["original_amount"] == 0
    assert body["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }
    assert "note" not in body["data"][0]
    assert _PRIVATE_NOTE not in response.text

    response_page_two = await client.get(
        "/api/transactions?month=2026-03&sort=amount_asc&page=2&page_size=2",
        headers=auth_headers(),
    )
    assert response_page_two.status_code == 200
    page_two_item = response_page_two.json()["data"][0]
    assert page_two_item["id"] == nullable_original.id
    assert page_two_item["currency"] == "TWD"
    assert page_two_item["original_amount"] is None


async def test_sensitive_merchant_is_rejected_without_echoing_card_number(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    session_bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=100,
        due_date=date(2026, 4, 15),
    )
    db_session.add(session_bill)
    await db_session.flush()
    db_session.add(
        Transaction(
            bill_id=session_bill.id,
            trans_date=date(2026, 3, 10),
            merchant=f"Unsafe merchant {_PAN}",
            amount=100,
            currency="TWD",
        )
    )
    await db_session.commit()

    with pytest.raises(AgentQueryError) as raised:
        await query_transactions(db_session, month="2026-03", q="Unsafe")

    assert raised.value.code == "needs_human"
    assert _PAN not in raised.value.message

    response = await client.get(
        "/api/transactions?month=2026-03&q=Unsafe",
        headers=auth_headers(),
    )
    assert response.status_code == 500
    assert _PAN not in response.text
