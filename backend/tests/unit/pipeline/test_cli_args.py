"""CLI argument parsing tests for pipeline __main__."""

import pytest

from ccas.pipeline.__main__ import _parse_args
from ccas.pipeline.options import PipelineOptions


class TestParseArgs:
    def test_no_args_returns_defaults(self):
        opts = _parse_args([])
        assert opts == PipelineOptions()

    def test_force_flag(self):
        opts = _parse_args(["--force"])
        assert opts.force is True

    def test_bank_code(self):
        opts = _parse_args(["--bank", "CTBC"])
        assert opts.bank_code == "CTBC"

    def test_year(self):
        opts = _parse_args(["--year", "2026"])
        assert opts.year == 2026

    def test_month(self):
        opts = _parse_args(["--month", "3"])
        assert opts.month == 3

    def test_full_combination(self):
        args = ["--force", "--bank", "CTBC", "--year", "2026", "--month", "3"]
        opts = _parse_args(args)
        expected = PipelineOptions(force=True, bank_code="CTBC", year=2026, month=3)
        assert opts == expected

    def test_invalid_month_exits(self):
        with pytest.raises(SystemExit):
            _parse_args(["--month", "13"])

    def test_invalid_month_zero_exits(self):
        with pytest.raises(SystemExit):
            _parse_args(["--month", "0"])
