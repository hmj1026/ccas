"""PipelineOptions unit tests.

Covers defaults, parameter combinations, gmail_date_filter edge cases,
and serialization round-trip.
"""

from datetime import date
from unittest.mock import patch

import pytest

from ccas.pipeline.options import PipelineOptions


class TestDefaults:
    def test_default_construction(self):
        opts = PipelineOptions()
        assert opts.force is False
        assert opts.bank_code is None
        assert opts.year is None
        assert opts.month is None

    def test_partial_params(self):
        opts = PipelineOptions(force=True, bank_code="CTBC")
        assert opts.force is True
        assert opts.bank_code == "CTBC"
        assert opts.year is None
        assert opts.month is None

    def test_frozen(self):
        opts = PipelineOptions()
        with pytest.raises(AttributeError):
            opts.force = True  # type: ignore[misc]


class TestGmailDateFilter:
    def test_no_year_no_month_returns_empty(self):
        opts = PipelineOptions()
        assert opts.gmail_date_filter() == ""

    def test_year_and_month(self):
        opts = PipelineOptions(year=2026, month=3)
        result = opts.gmail_date_filter()
        assert result == "after:2026/02/28 before:2026/04/01"

    def test_year_only(self):
        opts = PipelineOptions(year=2026)
        result = opts.gmail_date_filter()
        assert result == "after:2025/12/31 before:2027/01/01"

    def test_month_only_uses_current_year(self):
        with patch("ccas.pipeline.options.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            opts = PipelineOptions(month=3)
            result = opts.gmail_date_filter()
            assert result == "after:2026/02/28 before:2026/04/01"

    def test_december_crossover(self):
        opts = PipelineOptions(year=2026, month=12)
        result = opts.gmail_date_filter()
        assert result == "after:2026/11/30 before:2027/01/01"

    def test_january_crossover(self):
        opts = PipelineOptions(year=2026, month=1)
        result = opts.gmail_date_filter()
        assert result == "after:2025/12/31 before:2026/02/01"

    def test_leap_year_february(self):
        opts = PipelineOptions(year=2024, month=3)
        result = opts.gmail_date_filter()
        # Feb 2024 has 29 days (leap year)
        assert result == "after:2024/02/29 before:2024/04/01"

    def test_non_leap_year_february(self):
        opts = PipelineOptions(year=2025, month=3)
        result = opts.gmail_date_filter()
        # Feb 2025 has 28 days
        assert result == "after:2025/02/28 before:2025/04/01"

    def test_february_filter(self):
        opts = PipelineOptions(year=2026, month=2)
        result = opts.gmail_date_filter()
        assert result == "after:2026/01/31 before:2026/03/01"


class TestSerialization:
    def test_to_dict(self):
        opts = PipelineOptions(force=True, bank_code="CTBC", year=2026, month=3)
        d = opts.to_dict()
        assert d == {
            "force": True,
            "bank_code": "CTBC",
            "year": 2026,
            "month": 3,
        }

    def test_from_dict(self):
        d = {"force": True, "bank_code": "CTBC", "year": 2026, "month": 3}
        opts = PipelineOptions.from_dict(d)
        assert opts.force is True
        assert opts.bank_code == "CTBC"
        assert opts.year == 2026
        assert opts.month == 3

    def test_from_dict_none(self):
        opts = PipelineOptions.from_dict(None)
        assert opts == PipelineOptions()

    def test_from_dict_empty(self):
        opts = PipelineOptions.from_dict({})
        assert opts == PipelineOptions()

    def test_round_trip(self):
        original = PipelineOptions(force=True, bank_code="ESUN", year=2025)
        restored = PipelineOptions.from_dict(original.to_dict())
        assert restored == original
