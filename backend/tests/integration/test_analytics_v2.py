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
