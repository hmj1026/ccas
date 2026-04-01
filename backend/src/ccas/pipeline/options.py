"""Pipeline execution options."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta


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

    def __post_init__(self) -> None:
        if self.month is not None and not (1 <= self.month <= 12):
            raise ValueError(f"month must be 1-12, got {self.month}")
        if self.year is not None and not (2000 <= self.year <= 2099):
            raise ValueError(f"year must be 2000-2099, got {self.year}")

    def date_range(self) -> tuple[date, date] | None:
        """Return (start_inclusive, end_exclusive) date boundaries.

        When only ``month`` is set, defaults ``year`` to the current year.

        Returns:
            ``(first_day, first_day_after)`` or ``None`` if no date filtering.
        """
        effective_year = self.year
        effective_month = self.month

        if effective_year is None and effective_month is None:
            return None

        if effective_month is not None and effective_year is None:
            effective_year = date.today().year

        if effective_month is not None:
            if effective_year is None:
                raise ValueError("effective_year must not be None when month is set")
            start = date(effective_year, effective_month, 1)
            if effective_month == 12:
                end = date(effective_year + 1, 1, 1)
            else:
                end = date(effective_year, effective_month + 1, 1)
            return (start, end)

        # Year only
        if effective_year is None:
            raise ValueError("effective_year must not be None for year-only filter")
        return (date(effective_year, 1, 1), date(effective_year + 1, 1, 1))

    def gmail_date_filter(self) -> str:
        """根據 year/month 產生 Gmail 查詢日期篩選子句。

        Gmail query syntax:
        - ``after:YYYY/MM/DD`` (exclusive)
        - ``before:YYYY/MM/DD`` (exclusive)

        Returns:
            Gmail date filter clause, or empty string if no date filtering.
        """
        dr = self.date_range()
        if dr is None:
            return ""

        start, end = dr
        # Gmail after: is exclusive, so use day before start
        after_date = start - timedelta(days=1)
        return (
            f"after:{after_date.year}/{after_date.month:02d}/"
            f"{after_date.day:02d} "
            f"before:{end.year}/{end.month:02d}/"
            f"{end.day:02d}"
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
    def from_dict(cls, data: Mapping[str, object] | None) -> PipelineOptions:
        """Deserialize from dict (e.g. from RQ job kwargs)."""
        if not data:
            return cls()
        return cls(
            force=bool(data.get("force", False)),
            bank_code=data.get("bank_code"),  # type: ignore[arg-type]
            year=data.get("year"),  # type: ignore[arg-type]
            month=data.get("month"),  # type: ignore[arg-type]
        )
