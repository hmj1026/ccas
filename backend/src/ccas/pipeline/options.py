"""Pipeline execution options."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PipelineOptions:
    """Pipeline 執行參數。

    所有欄位皆有預設值，無參數建構等同預設行為（完整去重、全部銀行）。

    Attributes:
        force: 是否繞過去重強制重新處理。
        bank_code: 僅處理指定銀行（None 表示全部）。
        year: 篩選年份。
        month: 篩選月份（1-12）。
    """

    force: bool = False
    bank_code: str | None = None
    year: int | None = None
    month: int | None = None

    def gmail_date_filter(self) -> str:
        """根據 year/month 產生 Gmail 查詢日期篩選子句。

        Gmail query syntax:
        - ``after:YYYY/MM/DD`` (exclusive)
        - ``before:YYYY/MM/DD`` (exclusive)

        Returns:
            Gmail date filter clause, or empty string if no date filtering.
        """
        effective_year = self.year
        effective_month = self.month

        if effective_year is None and effective_month is None:
            return ""

        if effective_month is not None and effective_year is None:
            effective_year = date.today().year

        if effective_month is not None:
            assert effective_year is not None
            # after: last day of previous month (exclusive)
            # before: first day of next month (exclusive)
            if effective_month == 1:
                after_date = date(effective_year - 1, 12, 31)
            else:
                last_day_prev = calendar.monthrange(
                    effective_year, effective_month - 1
                )[1]
                after_date = date(effective_year, effective_month - 1, last_day_prev)

            if effective_month == 12:
                before_date = date(effective_year + 1, 1, 1)
            else:
                before_date = date(effective_year, effective_month + 1, 1)

            return (
                f"after:{after_date.year}/{after_date.month:02d}/"
                f"{after_date.day:02d} "
                f"before:{before_date.year}/{before_date.month:02d}/"
                f"{before_date.day:02d}"
            )

        # Year only
        assert effective_year is not None
        after_date = date(effective_year - 1, 12, 31)
        before_date = date(effective_year + 1, 1, 1)
        return (
            f"after:{after_date.year}/{after_date.month:02d}/"
            f"{after_date.day:02d} "
            f"before:{before_date.year}/{before_date.month:02d}/"
            f"{before_date.day:02d}"
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict for RQ job kwargs."""
        return {
            "force": self.force,
            "bank_code": self.bank_code,
            "year": self.year,
            "month": self.month,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> PipelineOptions:
        """Deserialize from dict (e.g. from RQ job kwargs)."""
        if not data:
            return cls()
        return cls(
            force=bool(data.get("force", False)),
            bank_code=data.get("bank_code"),  # type: ignore[arg-type]
            year=data.get("year"),  # type: ignore[arg-type]
            month=data.get("month"),  # type: ignore[arg-type]
        )
