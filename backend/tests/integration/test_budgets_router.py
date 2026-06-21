"""Integration tests for ``/api/budgets/*`` endpoints.

bills-management-and-insights §6.1-§6.5, §6.11-§6.12：CRUD + current-period
+ alerts list/acknowledge 端點覆蓋。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import (
    BankConfig,
    Bill,
    Budget,
    BudgetAlert,
    BudgetScope,
    Category,
    Transaction,
)
from tests.integration.conftest import auth_headers


async def _seed_budget(
    session: AsyncSession,
    *,
    scope: BudgetScope = BudgetScope.MONTHLY_TOTAL,
    scope_ref: str | None = None,
    amount: int = 10000,  # NTD 元 (whole dollars)
    threshold: int = 80,
    enabled: bool = True,
) -> Budget:
    b = Budget(
        scope=scope,
        scope_ref=scope_ref,
        amount_ntd=amount,
        alert_threshold_percent=threshold,
        enabled=enabled,
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b


async def _seed_bill_and_txns(
    session: AsyncSession,
    *,
    bank_code: str = "CTBC",
    billing_month: str | None = None,
    txns: list[tuple[int, str, str | None]] | None = None,
) -> Bill:
    """Seed bill + transactions. txns: (amount, merchant, category)."""
    if billing_month is None:
        today = date.today()
        billing_month = f"{today.year:04d}-{today.month:02d}"
    bank = BankConfig(
        bank_code=bank_code,
        bank_name=f"{bank_code}-name",
        gmail_filter=f"from:{bank_code.lower()}",
    )
    session.add(bank)
    bill = Bill(
        bank_code=bank_code,
        billing_month=billing_month,
        total_amount=sum(t[0] for t in (txns or [])),
        due_date=date.today() + timedelta(days=10),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()
    for amount, merchant, category in txns or []:
        t = Transaction(
            bill_id=bill.id,
            trans_date=date.today(),
            merchant=merchant,
            amount=amount,
            currency="TWD",
            category=category,
        )
        session.add(t)
    await session.commit()
    await session.refresh(bill)
    return bill


class TestListBudgets:
    async def test_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/budgets", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_filter_by_scope(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_budget(db_session, scope=BudgetScope.MONTHLY_TOTAL)
        await _seed_budget(db_session, scope=BudgetScope.MONTHLY_BANK, scope_ref="CTBC")
        resp = await client.get(
            "/api/budgets?scope=monthly_bank", headers=auth_headers()
        )
        items = resp.json()["data"]
        assert len(items) == 1
        assert items[0]["scope"] == "monthly_bank"


class TestCreateBudget:
    async def test_creates_monthly_total(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/budgets",
            json={
                "scope": "monthly_total",
                "amount_ntd": 30000,
                "alert_threshold_percent": 80,
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["scope"] == "monthly_total"
        assert data["scope_ref"] is None
        assert data["amount_ntd"] == 30000

    async def test_rejects_monthly_total_with_scope_ref(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/budgets",
            json={
                "scope": "monthly_total",
                "scope_ref": "should-not-be-here",
                "amount_ntd": 30000,
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_rejects_monthly_category_without_ref(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/budgets",
            json={
                "scope": "monthly_category",
                "amount_ntd": 5000,
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_rejects_unknown_category(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/budgets",
            json={
                "scope": "monthly_category",
                "scope_ref": "不存在的類別",
                "amount_ntd": 5000,
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_accepts_known_category(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(Category(keyword="food-key", category="餐飲"))
        await db_session.commit()

        resp = await client.post(
            "/api/budgets",
            json={
                "scope": "monthly_category",
                "scope_ref": "餐飲",
                "amount_ntd": 5000,
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 201

    async def test_rejects_unknown_bank(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/budgets",
            json={
                "scope": "monthly_bank",
                "scope_ref": "UNKNOWN",
                "amount_ntd": 5000,
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 422


class TestUpdateDeleteBudget:
    async def test_update_partial(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        b = await _seed_budget(db_session, amount=10000, threshold=80)
        resp = await client.put(
            f"/api/budgets/{b.id}",
            json={"alert_threshold_percent": 50, "enabled": False},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["alert_threshold_percent"] == 50
        assert data["enabled"] is False
        assert data["amount_ntd"] == 10000

    async def test_update_404(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/budgets/9999",
            json={"enabled": False},
            headers=auth_headers(),
        )
        assert resp.status_code == 404

    async def test_delete(self, client: AsyncClient, db_session: AsyncSession) -> None:
        b = await _seed_budget(db_session)
        resp = await client.delete(f"/api/budgets/{b.id}", headers=auth_headers())
        assert resp.status_code == 200
        # Re-list 應為空
        resp = await client.get("/api/budgets", headers=auth_headers())
        assert resp.json()["data"] == []

    async def test_delete_404(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/budgets/9999", headers=auth_headers())
        assert resp.status_code == 404

    async def test_delete_budget_with_alerts_cascades(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """刪除有歷史 BudgetAlert 的 budget：在 foreign_keys=ON 下不得 500，
        應連同清除其 alert 並回 200（alert 為內部通知記錄，無保留價值）。"""
        from sqlalchemy import select

        b = await _seed_budget(db_session)
        db_session.add(
            BudgetAlert(
                budget_id=b.id,
                period_year_month="2026-03",
                threshold_breached_percent=80,
                current_amount_ntd=9000,
                notified=True,
            )
        )
        await db_session.commit()

        resp = await client.delete(f"/api/budgets/{b.id}", headers=auth_headers())
        assert resp.status_code == 200

        remaining = (await db_session.execute(select(BudgetAlert))).scalars().all()
        assert remaining == []


class TestListWithCurrentPeriod:
    """R-budget-N+1：``?include_current_period=true`` 內聯當月累計，消除前端 1+N。"""

    async def test_current_period_omitted_by_default(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_budget(db_session, scope=BudgetScope.MONTHLY_TOTAL, amount=10000)
        resp = await client.get("/api/budgets", headers=auth_headers())
        assert resp.status_code == 200
        item = resp.json()["data"][0]
        # 預設不附帶（向下相容）：欄位存在但為 null。
        assert item.get("current_period") is None

    async def test_includes_current_period_inline(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(Category(keyword="food-key", category="餐飲"))
        await db_session.commit()
        total_b = await _seed_budget(
            db_session, scope=BudgetScope.MONTHLY_TOTAL, amount=10000, threshold=80
        )
        cat_b = await _seed_budget(
            db_session,
            scope=BudgetScope.MONTHLY_CATEGORY,
            scope_ref="餐飲",
            amount=5000,
        )
        bank_b = await _seed_budget(
            db_session,
            scope=BudgetScope.MONTHLY_BANK,
            scope_ref="CTBC",
            amount=8000,
        )
        await _seed_bill_and_txns(
            db_session,
            bank_code="CTBC",
            txns=[(3000, "M1", "餐飲"), (5000, "M2", "交通")],
        )

        resp = await client.get(
            "/api/budgets?include_current_period=true", headers=auth_headers()
        )
        assert resp.status_code == 200, resp.text
        by_id = {item["id"]: item for item in resp.json()["data"]}

        total_cp = by_id[total_b.id]["current_period"]
        assert total_cp is not None
        assert total_cp["current_amount_ntd"] == 8000
        assert total_cp["percent"] == 80.0
        assert total_cp["threshold_breached"] is True

        assert by_id[cat_b.id]["current_period"]["current_amount_ntd"] == 3000
        assert by_id[bank_b.id]["current_period"]["current_amount_ntd"] == 8000

    async def test_scope_filter_still_applies_with_current_period(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_budget(db_session, scope=BudgetScope.MONTHLY_TOTAL, amount=10000)
        await _seed_budget(
            db_session, scope=BudgetScope.MONTHLY_BANK, scope_ref="CTBC", amount=8000
        )
        resp = await client.get(
            "/api/budgets?scope=monthly_bank&include_current_period=true",
            headers=auth_headers(),
        )
        items = resp.json()["data"]
        assert len(items) == 1
        assert items[0]["scope"] == "monthly_bank"
        assert items[0]["current_period"] is not None


class TestCurrentPeriod:
    async def test_monthly_total_aggregation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        b = await _seed_budget(
            db_session, scope=BudgetScope.MONTHLY_TOTAL, amount=10000, threshold=80
        )
        await _seed_bill_and_txns(
            db_session,
            txns=[(3000, "M1", "餐飲"), (5000, "M2", "交通")],
        )

        resp = await client.get(
            f"/api/budgets/{b.id}/current-period", headers=auth_headers()
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["current_amount_ntd"] == 8000
        assert data["amount_ntd"] == 10000
        assert data["percent"] == 80.0
        assert data["threshold_breached"] is True

    async def test_monthly_category(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(Category(keyword="food-key", category="餐飲"))
        await db_session.commit()
        b = await _seed_budget(
            db_session,
            scope=BudgetScope.MONTHLY_CATEGORY,
            scope_ref="餐飲",
            amount=5000,
        )
        await _seed_bill_and_txns(
            db_session,
            txns=[(2000, "M1", "餐飲"), (5000, "M2", "交通")],
        )

        resp = await client.get(
            f"/api/budgets/{b.id}/current-period", headers=auth_headers()
        )
        data = resp.json()["data"]
        assert data["current_amount_ntd"] == 2000
        assert data["threshold_breached"] is False

    async def test_404_when_missing(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/budgets/9999/current-period", headers=auth_headers()
        )
        assert resp.status_code == 404


class TestActiveAlerts:
    async def test_returns_unack_recent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        b = await _seed_budget(db_session)
        today = date.today()
        ym = f"{today.year:04d}-{today.month:02d}"
        db_session.add(
            BudgetAlert(
                budget_id=b.id,
                period_year_month=ym,
                threshold_breached_percent=80,
                current_amount_ntd=8500,
                triggered_at=datetime.now(UTC),
            )
        )
        await db_session.commit()

        resp = await client.get("/api/budgets/alerts/active", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["budget_id"] == b.id
        assert data[0]["acknowledged_at"] is None

    async def test_acknowledge_removes_from_active(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        b = await _seed_budget(db_session)
        today = date.today()
        ym = f"{today.year:04d}-{today.month:02d}"
        alert = BudgetAlert(
            budget_id=b.id,
            period_year_month=ym,
            threshold_breached_percent=80,
            current_amount_ntd=8500,
            triggered_at=datetime.now(UTC),
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        resp = await client.post(
            f"/api/budgets/alerts/{alert.id}/acknowledge", headers=auth_headers()
        )
        assert resp.status_code == 200

        resp = await client.get("/api/budgets/alerts/active", headers=auth_headers())
        assert resp.json()["data"] == []

    async def test_acknowledge_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/budgets/alerts/9999/acknowledge", headers=auth_headers()
        )
        assert resp.status_code == 404
