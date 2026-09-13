"""Optional LLM reference parser for low-confidence bill candidates.

The Anthropic SDK is imported only when this adapter is called. A missing
credential, unavailable optional dependency, invalid response, timeout, or
failed result gate all return ``None`` so the parser intake can mark the
attachment for review without blocking the batch.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ccas.parser.result import (
    ParseResult,
    TransactionItem,
    finalize_parse_result,
    is_parse_result_acceptable,
)
from ccas.parser.result_schema import BillParseResultSchema

logger = logging.getLogger(__name__)

_MODEL_ID = "claude-sonnet-4-6"
_MAX_TOKENS = 2048


def _audit_identifier(bank_code: str, candidate: ParseResult | None) -> str:
    if candidate is not None:
        return f"{bank_code}:{candidate.billing_month}"
    return bank_code


def _candidate_payload(candidate: ParseResult | None) -> dict[str, object] | None:
    if candidate is None:
        return None
    return {
        "bank_code": candidate.bank_code,
        "billing_month": candidate.billing_month,
        "total_amount": candidate.total_amount,
        "due_date": candidate.due_date.isoformat(),
        "transactions": [
            {
                "trans_date": item.trans_date.isoformat(),
                "merchant": item.merchant,
                "amount": item.amount,
                "posting_date": (
                    item.posting_date.isoformat() if item.posting_date else None
                ),
                "currency": item.currency,
                "original_amount": item.original_amount,
                "card_last4": item.card_last4,
                "installment_current": item.installment_current,
                "installment_total": item.installment_total,
            }
            for item in candidate.transactions
        ],
    }


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return value


@dataclass
class BillLlmReference:
    """Anthropic-backed optional reference adapter."""

    api_key_provider: Callable[[], str]
    timeout_provider: Callable[[], float]

    async def parse(
        self,
        *,
        bank_code: str,
        source_text: str,
        candidate: ParseResult | None,
    ) -> ParseResult | None:
        identifier = _audit_identifier(bank_code, candidate)
        audit_timestamp = datetime.now(UTC).isoformat()
        self._audit(identifier, audit_timestamp)

        api_key = self.api_key_provider()
        if not api_key:
            logger.error(
                "bill_parse_llm_reference_unavailable",
                extra={
                    "event": "bill_parse_llm_reference_unavailable",
                    "bill_identifier": identifier,
                    "audit_timestamp": audit_timestamp,
                    "reason": "missing_anthropic_api_key",
                },
            )
            return None

        prompt = self._build_prompt(source_text, candidate)
        try:
            response_text = await asyncio.wait_for(
                self._request(prompt, api_key=api_key),
                timeout=self.timeout_provider(),
            )
        except TimeoutError:
            logger.warning(
                "bill_parse_llm_reference_timeout",
                extra={
                    "event": "bill_parse_llm_reference_timeout",
                    "bill_identifier": identifier,
                    "audit_timestamp": audit_timestamp,
                },
            )
            return None
        except Exception as exc:  # noqa: BLE001 -- optional route must fail closed
            logger.warning(
                "bill_parse_llm_reference_request_failed",
                extra={
                    "event": "bill_parse_llm_reference_request_failed",
                    "bill_identifier": identifier,
                    "audit_timestamp": audit_timestamp,
                    "error_type": type(exc).__name__,
                },
            )
            return None

        try:
            payload = json.loads(_strip_json_fence(response_text))
            validated = BillParseResultSchema.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "bill_parse_llm_reference_schema_rejected",
                extra={
                    "event": "bill_parse_llm_reference_schema_rejected",
                    "bill_identifier": identifier,
                    "audit_timestamp": audit_timestamp,
                    "error_type": type(exc).__name__,
                },
            )
            return None

        if validated.parse_confidence < 0.85 or validated.needs_review:
            logger.warning(
                "bill_parse_llm_reference_gate_rejected",
                extra={
                    "event": "bill_parse_llm_reference_gate_rejected",
                    "bill_identifier": identifier,
                    "audit_timestamp": audit_timestamp,
                    "reason_count": len(validated.review_reasons),
                },
            )
            return None

        result = ParseResult(
            bank_code=validated.bank_code,
            billing_month=validated.billing_month,
            total_amount=validated.total_amount,
            due_date=validated.due_date,
            transactions=tuple(
                TransactionItem(
                    trans_date=item.trans_date,
                    merchant=item.merchant,
                    amount=item.amount,
                    posting_date=item.posting_date,
                    currency=item.currency,
                    original_amount=item.original_amount,
                    card_last4=item.card_last4,
                    installment_current=item.installment_current,
                    installment_total=item.installment_total,
                )
                for item in validated.transactions
            ),
            due_date_estimated=validated.due_date_estimated,
        )
        result = finalize_parse_result(result, method="llm")
        if not is_parse_result_acceptable(result):
            logger.warning(
                "bill_parse_llm_reference_cross_check_rejected",
                extra={
                    "event": "bill_parse_llm_reference_cross_check_rejected",
                    "bill_identifier": identifier,
                    "audit_timestamp": audit_timestamp,
                    "reason_count": len(result.review_reasons),
                },
            )
            return None
        return result

    def _audit(self, identifier: str, timestamp: str) -> None:
        logger.info(
            "bill_parse_llm_reference_requested",
            extra={
                "event": "bill_parse_llm_reference_requested",
                "bill_identifier": identifier,
                "audit_timestamp": timestamp,
            },
        )

    @staticmethod
    def _build_prompt(source_text: str, candidate: ParseResult | None) -> str:
        # The source is sent to the model, but never interpolated into logs.
        return (
            "Extract one credit-card bill as JSON. Return only an object that "
            "matches the supplied bill parse schema. Preserve amounts as integer "
            "TWD units, use ISO dates, and do not invent missing fields.\n"
            "Existing candidate: "
            f"{json.dumps(_candidate_payload(candidate), ensure_ascii=False)}\n"
            f"OCR text:\n{source_text}"
        )

    async def _request(self, prompt: str, *, api_key: str) -> str:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("anthropic SDK is not installed") from exc

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=_MODEL_ID,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return str(getattr(block, "text", ""))
        return ""


def build_bill_llm_reference() -> BillLlmReference:
    """Build the production adapter using existing settings and credential."""
    from ccas.config import get_settings

    return BillLlmReference(
        api_key_provider=lambda: get_settings().anthropic_api_key.get_secret_value(),
        timeout_provider=lambda: get_settings().bill_parse_llm_timeout_seconds,
    )
