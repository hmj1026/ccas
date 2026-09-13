"""Tests for the optional bill parsing LLM reference adapter."""

import asyncio
import json
import logging
from datetime import date
from unittest.mock import AsyncMock

from ccas.parser.llm_reference import BillLlmReference
from ccas.parser.result import ParseResult, TransactionItem


def _candidate() -> ParseResult:
    return ParseResult(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=100,
        due_date=date(2026, 4, 15),
        transactions=(
            TransactionItem(
                trans_date=date(2026, 3, 10),
                merchant="全聯",
                amount=100,
                card_last4="1234",
            ),
        ),
    )


def _payload(**overrides: object) -> str:
    payload = {
        "bank_code": "CTBC",
        "billing_month": "2026-03",
        "total_amount": 100,
        "due_date": "2026-04-15",
        "transactions": [
            {
                "trans_date": "2026-03-10",
                "merchant": "全聯",
                "amount": 100,
                "card_last4": "1234",
            }
        ],
        "parse_confidence": 1.0,
        "needs_review": False,
        "review_reasons": [],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


async def test_valid_llm_response_is_finalized_as_llm() -> None:
    adapter = BillLlmReference(lambda: "sk-test", lambda: 1.0)
    adapter._request = AsyncMock(return_value=_payload())  # type: ignore[method-assign]

    result = await adapter.parse(
        bank_code="CTBC", source_text="帳單文字", candidate=_candidate()
    )

    assert result is not None
    assert result.parse_method == "llm"
    assert result.parse_confidence == 1.0
    assert result.needs_review is False
    adapter._request.assert_awaited_once()  # type: ignore[attr-defined]


async def test_llm_response_with_amount_mismatch_is_rejected() -> None:
    adapter = BillLlmReference(lambda: "sk-test", lambda: 1.0)
    adapter._request = AsyncMock(return_value=_payload(total_amount=101))  # type: ignore[method-assign]

    result = await adapter.parse(
        bank_code="CTBC", source_text="sensitive bill", candidate=None
    )

    assert result is None


async def test_llm_response_below_global_confidence_gate_is_rejected() -> None:
    adapter = BillLlmReference(lambda: "sk-test", lambda: 1.0)
    adapter._request = AsyncMock(return_value=_payload(parse_confidence=0.83))  # type: ignore[method-assign]

    assert (
        await adapter.parse(bank_code="CTBC", source_text="bill", candidate=None)
        is None
    )


async def test_missing_credential_does_not_send_request(caplog) -> None:
    adapter = BillLlmReference(lambda: "", lambda: 1.0)
    adapter._request = AsyncMock()  # type: ignore[method-assign]

    with caplog.at_level(logging.INFO, logger="ccas.parser.llm_reference"):
        result = await adapter.parse(
            bank_code="CTBC", source_text="private card details", candidate=_candidate()
        )

    assert result is None
    adapter._request.assert_not_awaited()  # type: ignore[attr-defined]
    assert "private card details" not in caplog.text


async def test_timeout_isolated_to_current_reference_call() -> None:
    async def never_finishes(*args, **kwargs) -> str:
        await asyncio.sleep(1)
        return "{}"

    adapter = BillLlmReference(lambda: "sk-test", lambda: 0.001)
    adapter._request = never_finishes  # type: ignore[method-assign]

    assert (
        await adapter.parse(bank_code="CTBC", source_text="bill", candidate=None)
        is None
    )
