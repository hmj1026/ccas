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


class TestValidation:
    def test_valid_construction(self):
        opts = PipelineOptions(year=2026, month=3)
        assert opts.year == 2026
        assert opts.month == 3

    @pytest.mark.parametrize("month", [0, -1, 13, 100])
    def test_invalid_month_raises(self, month):
        with pytest.raises(ValueError, match="month must be 1-12"):
            PipelineOptions(month=month)

    @pytest.mark.parametrize("year", [0, 1999, 2100, -1, 9999])
    def test_invalid_year_raises(self, year):
        with pytest.raises(ValueError, match="year must be 2000-2099"):
            PipelineOptions(year=year)

    def test_boundary_month_valid(self):
        assert PipelineOptions(month=1).month == 1
        assert PipelineOptions(month=12).month == 12

    def test_boundary_year_valid(self):
        assert PipelineOptions(year=2000).year == 2000
        assert PipelineOptions(year=2099).year == 2099


class TestDateRange:
    def test_no_year_no_month_returns_none(self):
        assert PipelineOptions().date_range() is None

    def test_year_and_month(self):
        opts = PipelineOptions(year=2026, month=3)
        assert opts.date_range() == (date(2026, 3, 1), date(2026, 4, 1))

    def test_year_only(self):
        opts = PipelineOptions(year=2026)
        assert opts.date_range() == (date(2026, 1, 1), date(2027, 1, 1))

    def test_month_only_uses_current_year(self):
        with patch("ccas.pipeline.options.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            opts = PipelineOptions(month=3)
            assert opts.date_range() == (date(2026, 3, 1), date(2026, 4, 1))

    def test_december(self):
        opts = PipelineOptions(year=2026, month=12)
        assert opts.date_range() == (date(2026, 12, 1), date(2027, 1, 1))


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


class TestStageFields:
    def test_default_stages_none(self):
        opts = PipelineOptions()
        assert opts.from_stage is None
        assert opts.to_stage is None

    def test_from_stage_only(self):
        opts = PipelineOptions(from_stage="decrypt")
        assert opts.from_stage == "decrypt"
        assert opts.to_stage is None

    def test_to_stage_only(self):
        opts = PipelineOptions(to_stage="parse")
        assert opts.to_stage == "parse"
        assert opts.from_stage is None

    def test_both_stages(self):
        opts = PipelineOptions(from_stage="decrypt", to_stage="classify")
        assert opts.from_stage == "decrypt"
        assert opts.to_stage == "classify"


class TestSerialization:
    def test_to_dict(self):
        opts = PipelineOptions(force=True, bank_code="CTBC", year=2026, month=3)
        d = opts.to_dict()
        assert d == {
            "force": True,
            "bank_code": "CTBC",
            "year": 2026,
            "month": 3,
            "from_stage": None,
            "to_stage": None,
        }

    def test_to_dict_with_stages(self):
        opts = PipelineOptions(from_stage="parse", to_stage="notify")
        d = opts.to_dict()
        assert d["from_stage"] == "parse"
        assert d["to_stage"] == "notify"

    def test_from_dict(self):
        d = {"force": True, "bank_code": "CTBC", "year": 2026, "month": 3}
        opts = PipelineOptions.from_dict(d)
        assert opts.force is True
        assert opts.bank_code == "CTBC"
        assert opts.year == 2026
        assert opts.month == 3
        assert opts.from_stage is None
        assert opts.to_stage is None

    def test_from_dict_with_stages(self):
        d = {"from_stage": "decrypt", "to_stage": "classify"}
        opts = PipelineOptions.from_dict(d)
        assert opts.from_stage == "decrypt"
        assert opts.to_stage == "classify"

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

    def test_round_trip_with_stages(self):
        original = PipelineOptions(from_stage="parse", to_stage="classify")
        restored = PipelineOptions.from_dict(original.to_dict())
        assert restored == original
