"""Contract tests for Agent reconciliation identity and sensitive data handling."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from ccas.services.identity import (
    build_bill_reconciliation_key,
    build_transaction_reconciliation_key,
    canonical_quote,
)
from ccas.services.schemas import AgentQueryError


async def test_canonical_quote_escapes_utf8_and_reserved_delimiters() -> None:
    assert canonical_quote("台北: A/B#") == "%E5%8F%B0%E5%8C%97%3A%20A%2FB%23"


@pytest.mark.parametrize(
    ("cards", "expected"),
    [
        (["5678", "1234", "1234"], "CTBC:2026-03:1234,5678"),
        ([], "CTBC:2026-03:due-2026-04-15"),
    ],
)
async def test_bill_identity_sorts_and_deduplicates_cards(
    cards: list[str], expected: str
) -> None:
    assert (
        build_bill_reconciliation_key(
            bank_code="CTBC",
            billing_month="2026-03",
            card_last4s=cards,
            due_date=date(2026, 4, 15),
        )
        == expected
    )


@pytest.mark.parametrize(
    ("amount", "merchant", "dup_ordinal", "expected"),
    [
        (
            -250,
            "Cafe:台北",
            1,
            "42:2026-03-14:-250:Cafe%3A%E5%8F%B0%E5%8C%97",
        ),
        (
            -250,
            "Cafe:台北",
            2,
            "42:2026-03-14:-250:Cafe%3A%E5%8F%B0%E5%8C%97#2",
        ),
    ],
)
async def test_transaction_identity_preserves_negative_amount_and_duplicate_ordinal(
    amount: int,
    merchant: str,
    dup_ordinal: int,
    expected: str,
) -> None:
    assert (
        build_transaction_reconciliation_key(
            bill_id=42,
            trans_date=date(2026, 3, 14),
            amount=amount,
            merchant=merchant,
            dup_ordinal=dup_ordinal,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("builder", "kwargs", "secret"),
    [
        (
            build_bill_reconciliation_key,
            {
                "bank_code": "CTBC password=card-secret",
                "billing_month": "2026-03",
                "card_last4s": [],
                "due_date": date(2026, 4, 15),
            },
            "card-secret",
        ),
        (
            build_bill_reconciliation_key,
            {
                "bank_code": "CTBC 4111111111111111",
                "billing_month": "2026-03",
                "card_last4s": [],
                "due_date": date(2026, 4, 15),
            },
            "4111111111111111",
        ),
        (
            build_transaction_reconciliation_key,
            {
                "bill_id": 42,
                "trans_date": date(2026, 3, 14),
                "amount": -250,
                "merchant": "Cafe token=merchant-secret",
            },
            "merchant-secret",
        ),
        (
            build_transaction_reconciliation_key,
            {
                "bill_id": 42,
                "trans_date": date(2026, 3, 14),
                "amount": -250,
                "merchant": "Cafe 4111111111111111",
            },
            "4111111111111111",
        ),
    ],
)
async def test_sensitive_identity_component_fails_safe(
    builder: Callable[..., str], kwargs: dict[str, Any], secret: str
) -> None:
    with pytest.raises(AgentQueryError) as caught:
        builder(**kwargs)

    error = caught.value
    assert error.code == "needs_human"
    assert error.needs_human is True
    assert secret not in error.message
