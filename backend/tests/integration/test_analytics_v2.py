"""Integration tests for /api/analytics/* v2 endpoints (§7).

涵蓋：
- compare/banks
- compare/years (total / count)
- top-merchants (limit, period)
- categories/compare
"""

from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


async def _seed_bank(session: AsyncSession, code: str, name: str) -> None:
    session.add(BankConfig(bank_code=code, bank_name=name, gmail_filter=f"from:{code}"))


async def _seed_bill_with_txns(
    session: AsyncSession,
    *,
    bank_code: str,
    billing_month: str,
    txns: list[tuple[int, str, str | None]],
) -> Bill:
    bill = Bill(
        bank_code=bank_code,
        billing_month=billing_month,
        total_amount=sum(t[0] for t in txns),
        due_date=date.today() + timedelta(days=10),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()
    for amt, merchant, cat in txns:
        session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date.today(),
                merchant=merchant,
                amount=amt,
                currency="TWD",
                category=cat,
            )
        )
    await session.commit()
    await session.refresh(bill)
    return bill


class TestCompareBanks:
    async def test_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/analytics/compare/banks", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_groups_by_bank(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await _seed_bank(db_session, "ESUN", "玉山")
        await db_session.commit()

        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(1000, "M1", "餐飲"), (2000, "M2", "交通")],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="ESUN",
            billing_month="2026-05",
            txns=[(500, "M3", None)],
        )

        resp = await client.get(
            "/api/analytics/compare/banks?month=2026-05",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # sorted DESC by total
        assert data[0]["bank_code"] == "CTBC"
        assert data[0]["bank_name"] == "中國信託"
        assert data[0]["total"] == 3000
        assert data[1]["bank_code"] == "ESUN"
        assert data[1]["total"] == 500


class TestCompareYears:
    async def test_total_metric(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2025-03",
            txns=[(5000, "M1", None)],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-04",
            txns=[(8000, "M2", None), (2000, "M3", None)],
        )

        resp = await client.get(
            "/api/analytics/compare/years?metric=total",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # ASC by year
        years = {row["year"]: row["value"] for row in data}
        assert years[2025] == 5000
        assert years[2026] == 10000

    async def test_count_metric(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-04",
            txns=[(100, "M1", None), (200, "M2", None), (300, "M3", None)],
        )

        resp = await client.get(
            "/api/analytics/compare/years?metric=count",
            headers=auth_headers(),
        )
        data = resp.json()["data"]
        assert any(row["year"] == 2026 and row["value"] == 3 for row in data)


class TestTopMerchants:
    async def test_aggregates_and_limits(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[
                (500, "STARBUCKS", "餐飲"),
                (300, "STARBUCKS", "餐飲"),
                (1000, "UBER", "交通"),
                (200, "7-11", "便利"),
            ],
        )

        resp = await client.get(
            "/api/analytics/top-merchants?limit=2&period=all",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        # UBER 1000 vs STARBUCKS 800 — UBER first
        assert data[0]["merchant"] == "UBER"
        assert data[0]["total"] == 1000
        assert data[0]["count"] == 1
        assert data[1]["merchant"] == "STARBUCKS"
        assert data[1]["total"] == 800
        assert data[1]["count"] == 2

    async def test_empty(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/analytics/top-merchants?limit=5",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestCategoriesCompareWithPrevious:
    async def test_returns_previous_month_diff(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-04",
            txns=[(1000, "M1", "餐飲"), (500, "M2", "交通")],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(1500, "M3", "餐飲"), (200, "M4", "交通")],
        )

        resp = await client.get(
            "/api/analytics/categories/compare?month=2026-05",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = {row["category"]: row for row in resp.json()["data"]}
        # 餐飲：1000 → 1500，+50%
        assert data["餐飲"]["total"] == 1500
        assert data["餐飲"]["previous_total"] == 1000
        assert data["餐飲"]["change_percent"] == 50.0
        # 交通：500 → 200，-60%
        assert data["交通"]["total"] == 200
        assert data["交通"]["previous_total"] == 500
        assert data["交通"]["change_percent"] == -60.0

    async def test_new_category_without_previous_has_null_compare(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """(a) 本月新類別、前月無資料 → previous_total null、change_percent null。"""
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        # Previous month (2026-04) has only 餐飲; current month (2026-05) adds 旅遊.
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-04",
            txns=[(1000, "M1", "餐飲")],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(1000, "M2", "餐飲"), (777, "M3", "旅遊")],
        )

        resp = await client.get(
            "/api/analytics/categories/compare?month=2026-05",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = {row["category"]: row for row in resp.json()["data"]}
        assert data["旅遊"]["total"] == 777
        assert data["旅遊"]["previous_total"] is None
        assert data["旅遊"]["change_percent"] is None

    async def test_zero_previous_total_yields_null_change_no_crash(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """(b) 前月 total 為 0（充值+退款互抵）→ change_percent null，不除零。"""
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        # Previous month 娛樂 nets to 0 (a charge fully refunded — refunds are
        # stored as negative line items, not dropped).
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-04",
            txns=[(500, "CHARGE", "娛樂"), (-500, "REFUND", "娛樂")],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(300, "M1", "娛樂")],
        )

        resp = await client.get(
            "/api/analytics/categories/compare?month=2026-05",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = {row["category"]: row for row in resp.json()["data"]}
        assert data["娛樂"]["total"] == 300
        assert data["娛樂"]["previous_total"] == 0
        # Zero-previous guard: no divide-by-zero, change_percent is null.
        assert data["娛樂"]["change_percent"] is None

    async def test_previous_only_category_appears_with_minus_100(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """(c) 前月有、本月消失的類別仍出現：total=0、change_percent=-100。"""
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        # 交通 present last month (2026-04), absent this month (2026-05).
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-04",
            txns=[(1000, "M1", "餐飲"), (800, "M2", "交通")],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(1200, "M3", "餐飲")],
        )

        resp = await client.get(
            "/api/analytics/categories/compare?month=2026-05",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = {row["category"]: row for row in resp.json()["data"]}
        # 交通 no longer silently vanishes: full downward trend.
        assert "交通" in data
        assert data["交通"]["total"] == 0
        assert data["交通"]["previous_total"] == 800
        assert data["交通"]["change_percent"] == -100.0

    async def test_compare_requires_month(self, client: AsyncClient) -> None:
        """categories/compare 未帶 month 應回 422。"""
        resp = await client.get(
            "/api/analytics/categories/compare",
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_legacy_categories_without_compare(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """基礎 /categories 端點應維持 CategoryItem schema（不含比較欄位）。"""
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(1000, "M1", "餐飲")],
        )

        resp = await client.get(
            "/api/analytics/categories?month=2026-05",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert items[0]["category"] == "餐飲"
        assert items[0]["total"] == 1000
        # legacy schema 不含 previous_total / change_percent
        assert "previous_total" not in items[0]


class TestCompareBanksYearFilter:
    """R17：compare/banks 的 year 過濾分支（既有測試只覆蓋 month）。"""

    async def test_year_filter_groups_only_matching_year(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2025-05",
            txns=[(1000, "M1", None)],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month="2026-05",
            txns=[(2000, "M2", None)],
        )
        resp = await client.get(
            "/api/analytics/compare/banks?year=2026",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 僅 2026 年帳單計入
        assert data == [{"bank_code": "CTBC", "bank_name": "中國信託", "total": 2000}]


class TestTopMerchantsPeriodBranches:
    """R17：top-merchants 的 period=month / period=year 過濾分支。"""

    async def _seed_two_months(self, db_session: AsyncSession) -> None:
        await _seed_bank(db_session, "CTBC", "中國信託")
        await db_session.commit()
        today = date.today()
        this_month = f"{today.year:04d}-{today.month:02d}"
        prev_year = f"{today.year - 1:04d}-{today.month:02d}"
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month=this_month,
            txns=[(900, "NOW_MERCHANT", None)],
        )
        await _seed_bill_with_txns(
            db_session,
            bank_code="CTBC",
            billing_month=prev_year,
            txns=[(100, "OLD_MERCHANT", None)],
        )

    async def test_period_month_filters_current_month(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await self._seed_two_months(db_session)
        resp = await client.get(
            "/api/analytics/top-merchants?period=month",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        merchants = {row["merchant"] for row in resp.json()["data"]}
        assert "NOW_MERCHANT" in merchants
        assert "OLD_MERCHANT" not in merchants

    async def test_period_year_filters_current_year(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await self._seed_two_months(db_session)
        resp = await client.get(
            "/api/analytics/top-merchants?period=year",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        merchants = {row["merchant"] for row in resp.json()["data"]}
        assert "NOW_MERCHANT" in merchants
        assert "OLD_MERCHANT" not in merchants


class TestAnalyticsAuthAndValidation:
    """R31：analytics v2 端點的 401（未授權）與 422（參數驗證）路徑。"""

    async def test_compare_banks_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/analytics/compare/banks")
        assert resp.status_code == 401

    async def test_top_merchants_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/analytics/top-merchants")
        assert resp.status_code == 401

    async def test_compare_banks_rejects_bad_month_pattern(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get(
            "/api/analytics/compare/banks?month=2026-13",
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_top_merchants_rejects_out_of_range_limit(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get(
            "/api/analytics/top-merchants?limit=0",
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_compare_years_rejects_bad_metric(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/analytics/compare/years?metric=bogus",
            headers=auth_headers(),
        )
        assert resp.status_code == 422
