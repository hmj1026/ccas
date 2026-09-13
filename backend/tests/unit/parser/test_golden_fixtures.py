"""Desensitized golden outcomes for every parser route."""

import json
from pathlib import Path

import pytest

from ccas.parser.result_schema import BillParseResultSchema

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/parser/golden"


@pytest.mark.parametrize(
    "fixture_name",
    ["rules-only", "ocr-fallback", "llm-assisted", "low-confidence", "failed"],
)
def test_golden_fixture_captures_route_and_persistence(fixture_name: str) -> None:
    fixture = json.loads((_FIXTURE_DIR / f"{fixture_name}.json").read_text())

    assert fixture["name"] == fixture_name
    assert fixture["persistence"]["attachment_status"] in {"parsed", "parse_failed"}
    result = fixture["result"]
    if result is None:
        assert fixture["persistence"]["bill_created"] is False
        return

    parsed = BillParseResultSchema.model_validate(result)
    assert parsed.parse_method in {"rules", "ocr", "llm"}
    assert 0.0 <= parsed.parse_confidence <= 1.0
    if parsed.needs_review:
        assert parsed.review_reasons
        assert fixture["persistence"]["bill_created"] is False
    else:
        assert parsed.review_reasons == []
        assert fixture["persistence"]["bill_created"] is True
