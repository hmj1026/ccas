"""Unit tests for ``ccas.api.routers.analytics_v2._period_window``.

純函數，不依賴 DB；驗證 month / year / all 與 offset 計算（含跨年）。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from ccas.api.routers.analytics_v2 import _period_window


class TestPeriodWindow:
    def test_all_returns_none(self):
        assert _period_window("all", offset_months=0) is None

    @patch("ccas.api.routers.analytics_v2.date")
    def test_month_no_offset(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 15)
        # date(...) constructor still real — we only stub today()
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _period_window("month", offset_months=0) == "2026-05"

    @patch("ccas.api.routers.analytics_v2.date")
    def test_month_offset_within_year(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _period_window("month", offset_months=2) == "2026-03"

    @patch("ccas.api.routers.analytics_v2.date")
    def test_month_offset_crosses_year_boundary(self, mock_date):
        mock_date.today.return_value = date(2026, 2, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        # 2026-02 - 5 months → 2025-09
        assert _period_window("month", offset_months=5) == "2025-09"

    @patch("ccas.api.routers.analytics_v2.date")
    def test_month_offset_crosses_multiple_years(self, mock_date):
        mock_date.today.return_value = date(2026, 1, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        # 2026-01 - 13 months → 2024-12
        assert _period_window("month", offset_months=13) == "2024-12"

    @patch("ccas.api.routers.analytics_v2.date")
    def test_year_no_offset(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _period_window("year", offset_months=0) == "2026"

    @patch("ccas.api.routers.analytics_v2.date")
    def test_year_with_offset(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _period_window("year", offset_months=2) == "2024"
