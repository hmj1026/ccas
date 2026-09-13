"""Tests for the parser result contract and generated schema."""

import json
from datetime import date
from pathlib import Path

from ccas.parser.result import (
    PARSE_CONFIDENCE_THRESHOLD,
    ParseResult,
    TransactionItem,
    assess_parse_result,
    finalize_parse_result,
    is_parse_result_acceptable,
)
from ccas.parser.result_schema import BillParseResultSchema


def _result(**overrides: object) -> ParseResult:
    values: dict[str, object] = {
        "bank_code": "CTBC",
        "billing_month": "2026-03",
        "total_amount": 100,
        "due_date": date(2026, 4, 15),
        "transactions": (
            TransactionItem(
                trans_date=date(2026, 3, 10),
                merchant="全聯",
                amount=100,
                card_last4="1234",
            ),
        ),
    }
    values.update(overrides)
    return ParseResult(**values)  # type: ignore[arg-type]


def test_existing_parser_defaults_are_rules_and_full_confidence() -> None:
    result = _result()

    assert result.parse_method == "rules"
    assert result.parse_confidence == 1.0
    assert result.needs_review is False
    assert result.review_reasons == ()


def test_three_of_four_fields_rounds_half_up_to_083() -> None:
    result = _result(bank_code="")

    assessment = assess_parse_result(result)

    assert assessment.field_score == 0.75
    assert assessment.check_score == 1.0
    assert assessment.parse_confidence == 0.83
    assert assessment.needs_review is True
    assert "bank_code" in " ".join(assessment.review_reasons)
    assert PARSE_CONFIDENCE_THRESHOLD == 0.85


def test_cross_check_failure_requires_review() -> None:
    result = _result(total_amount=101)

    assessment = assess_parse_result(result)

    assert assessment.parse_confidence == 0.9
    assert assessment.needs_review is True
    assert any("總額" in reason for reason in assessment.review_reasons)
    assert (
        is_parse_result_acceptable(finalize_parse_result(result, method="ocr")) is False
    )


def test_full_valid_result_is_acceptable_with_confidence_one() -> None:
    result = finalize_parse_result(_result(), method="ocr")

    assert result.parse_method == "ocr"
    assert result.parse_confidence == 1.0
    assert result.needs_review is False
    assert result.review_reasons == ()
    assert is_parse_result_acceptable(result)


def test_generated_schema_matches_checked_in_artifact() -> None:
    schema_path = (
        Path(__file__).resolve().parents[4] / "schemas/bill_parse_result.schema.json"
    )
    checked_in = json.loads(schema_path.read_text())

    assert checked_in == BillParseResultSchema.model_json_schema()
