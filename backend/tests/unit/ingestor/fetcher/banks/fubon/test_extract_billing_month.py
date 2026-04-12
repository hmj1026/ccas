"""Unit tests for _extract_billing_month — YYYY年MM月 regex extraction."""

from __future__ import annotations

from ccas.ingestor.fetcher.banks.fubon import _extract_billing_month


class TestExtractBillingMonth:

    def test_standard_format(self):
        assert _extract_billing_month("2026年03月信用卡帳單") == "2026-03"

    def test_single_digit_month(self):
        assert _extract_billing_month("2026年3月") == "2026-03"

    def test_december(self):
        assert _extract_billing_month("2025年12月帳單") == "2025-12"

    def test_no_match(self):
        assert _extract_billing_month("Hello world") is None

    def test_embedded_in_html(self):
        assert _extract_billing_month("<p>2026年12月帳單</p>") == "2026-12"

    def test_with_spaces(self):
        assert _extract_billing_month("2026 年 3 月") == "2026-03"

    def test_empty_string(self):
        assert _extract_billing_month("") is None

    def test_picks_first_match(self):
        result = _extract_billing_month("2026年03月和2026年04月")
        assert result == "2026-03"
