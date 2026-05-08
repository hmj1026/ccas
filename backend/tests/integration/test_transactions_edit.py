"""Integration tests for ``/api/transactions/{id}`` edit endpoints.

bills-management-and-insights §3：

- ``PUT /api/transactions/{id}``：partial update（category/note/tags/merchant_alias）
  改 category 同步設 manual_category_override=true
- ``POST /api/transactions/{id}/note``：僅更新 note
- ``DELETE /api/transactions/{id}/manual-override``：清除 flag 並重新走 classify
- ``GET /api/transactions/{id}``：詳情頁讀取
"""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import Bill, Category, Transaction
from tests.integration.conftest import auth_headers


async def _seed_bill_and_txn(
    session: AsyncSession,
    *,
    merchant: str = "星巴克",
    category: str | None = None,
    note: str | None = None,
    manual_override: bool = False,
) -> Transaction:
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=200,
        due_date=date(2026, 4, 15),
    )
    session.add(bill)
    await session.flush()
    txn = Transaction(
        bill_id=bill.id,
        trans_date=date(2026, 3, 1),
        merchant=merchant,
        amount=200,
        currency="TWD",
        category=category,
        note=note,
        manual_category_override=manual_override,
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)
    return txn


async def _seed_category(session: AsyncSession, name: str) -> Category:
    cat = Category(keyword=f"{name}-key", category=name)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


class TestGetTransactionDetail:
    async def test_get_returns_full_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session, category="餐飲")
        resp = await client.get(f"/api/transactions/{txn.id}", headers=auth_headers())
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["id"] == txn.id
        assert body["category"] == "餐飲"
        assert body["manual_category_override"] is False
        assert body["tags"] == []
        assert body["merchant_alias"] == ""
        assert "updated_at" in body

    async def test_get_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get("/api/transactions/9999", headers=auth_headers())
        assert resp.status_code == 404

    async def test_get_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get("/api/transactions/1")
        assert resp.status_code == 401


class TestPutTransaction:
    async def test_update_category_sets_manual_override(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session, category="餐飲")
        new_cat = await _seed_category(db_session, "購物")

        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"category_id": new_cat.id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["category"] == "購物"
        assert body["manual_category_override"] is True

    async def test_update_note_does_not_set_manual_override(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session, category="餐飲")
        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"note": "公司聚餐"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["note"] == "公司聚餐"
        assert body["manual_category_override"] is False
        assert body["category"] == "餐飲"  # unchanged

    async def test_update_tags_and_merchant_alias(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session)
        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"tags": ["業務", "可報銷"], "merchant_alias": "Starbucks 信義店"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["tags"] == ["業務", "可報銷"]
        assert body["merchant_alias"] == "Starbucks 信義店"

    async def test_update_invalid_category_id_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session)
        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"category_id": 9999},
        )
        assert resp.status_code == 422

    async def test_update_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.put(
            "/api/transactions/9999",
            headers=auth_headers(),
            json={"note": "x"},
        )
        assert resp.status_code == 404

    async def test_update_empty_body_is_noop(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session, category="餐飲")
        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["category"] == "餐飲"

    async def test_update_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.put("/api/transactions/1", json={"note": "x"})
        assert resp.status_code == 401


class TestPostNote:
    async def test_post_note_updates_only_note(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session, category="餐飲")
        resp = await client.post(
            f"/api/transactions/{txn.id}/note",
            headers=auth_headers(),
            json={"note": "好喝"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["note"] == "好喝"
        assert body["category"] == "餐飲"  # unchanged
        assert body["manual_category_override"] is False

    async def test_post_note_empty_string_clears_note(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session, note="old")
        resp = await client.post(
            f"/api/transactions/{txn.id}/note",
            headers=auth_headers(),
            json={"note": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["note"] == ""

    async def test_post_note_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/transactions/9999/note",
            headers=auth_headers(),
            json={"note": "x"},
        )
        assert resp.status_code == 404


class TestDeleteManualOverride:
    async def test_delete_clears_flag_and_reclassifies(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Seed engine rule: keyword=星巴克 → category=餐飲，讓 classify 真能 hit
        db_session.add(Category(keyword="星巴克", category="餐飲"))
        await db_session.commit()
        # Manually set to 購物 with manual_override=true
        txn = await _seed_bill_and_txn(
            db_session,
            merchant="星巴克",
            category="購物",
            manual_override=True,
        )
        resp = await client.delete(
            f"/api/transactions/{txn.id}/manual-override",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["manual_category_override"] is False
        # 星巴克-key 對應 category=餐飲，重新 classify 應該得到 "餐飲"
        assert body["category"] == "餐飲"

    async def test_delete_when_override_false_is_noop(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(Category(keyword="星巴克", category="餐飲"))
        await db_session.commit()
        txn = await _seed_bill_and_txn(
            db_session, merchant="星巴克", category=None, manual_override=False
        )
        resp = await client.delete(
            f"/api/transactions/{txn.id}/manual-override",
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["manual_category_override"] is False

    async def test_delete_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.delete(
            "/api/transactions/9999/manual-override", headers=auth_headers()
        )
        assert resp.status_code == 404


class TestDeleteManualOverrideUserRulePath:
    """DELETE /manual-override 走 user_rules → engine 優先序；user_rules 命中時勝出。"""

    async def test_delete_user_rule_wins_over_engine(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from ccas.storage.models import PatternType, UserClassificationRule

        # engine 規則：星巴克 → 餐飲
        cat_food = Category(keyword="星巴克", category="餐飲")
        # user rule 把同一商家覆寫成「商務」
        cat_business = Category(keyword="商務-key", category="商務")
        db_session.add_all([cat_food, cat_business])
        await db_session.commit()
        await db_session.refresh(cat_business)
        db_session.add(
            UserClassificationRule(
                pattern="星巴克",
                pattern_type=PatternType.KEYWORD,
                category_id=cat_business.id,
                priority=10,
                enabled=True,
            )
        )
        await db_session.commit()

        txn = await _seed_bill_and_txn(
            db_session,
            merchant="星巴克",
            category="購物",
            manual_override=True,
        )
        resp = await client.delete(
            f"/api/transactions/{txn.id}/manual-override",
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["manual_category_override"] is False
        # user rule 應該勝出，而非 engine 結果（餐飲）
        assert body["category"] == "商務"


class TestUpdateTagsCanClear:
    async def test_put_tags_empty_list_clears_existing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        txn = await _seed_bill_and_txn(db_session)
        # 先設一些 tags
        resp1 = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"tags": ["A", "B"]},
        )
        assert resp1.json()["data"]["tags"] == ["A", "B"]
        # 再以空 list 清除
        resp2 = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"tags": []},
        )
        assert resp2.status_code == 200
        assert resp2.json()["data"]["tags"] == []


class TestManualOverridePreservedAfterReclassify:
    """§3.6 / §15.1 端對端：編輯 → 重跑 → 保留 category。"""

    async def test_manual_override_survives_run_classify_job(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from sqlalchemy import select as sa_select

        # 1. 先建立 keyword → category 規則（engine 真能命中星巴克）
        db_session.add_all(
            [
                Category(keyword="星巴克", category="餐飲"),
                Category(keyword="購物-key", category="購物"),
            ]
        )
        await db_session.commit()
        purchase_cat = (
            await db_session.execute(
                sa_select(Category).where(Category.category == "購物")
            )
        ).scalar_one()
        # 2. 新建 unclassified 交易
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=200,
            due_date=date(2026, 4, 15),
        )
        db_session.add(bill)
        await db_session.flush()
        txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="星巴克",
            amount=200,
        )
        db_session.add(txn)
        await db_session.commit()
        await db_session.refresh(txn)

        # 3. 跑 classify → 預期成 "餐飲"
        from ccas.classifier.job import run_classify_job

        await run_classify_job(db_session)
        await db_session.refresh(txn)
        assert txn.category == "餐飲"

        # 4. 編輯 category 為「購物」，manual_override=true
        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"category_id": purchase_cat.id},
        )
        assert resp.status_code == 200
        await db_session.refresh(txn)
        assert txn.category == "購物"
        assert txn.manual_category_override is True

        # 5. 重跑 classify 多次 → category 不應被覆蓋
        for _ in range(5):
            await run_classify_job(db_session)
        await db_session.refresh(txn)
        assert txn.category == "購物"
        assert txn.manual_category_override is True

    async def test_manual_override_survives_run_reclassify_job(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """§15.1 真實路徑：run_reclassify_job 撈 fetch_all_transactions，
        會真正觸碰已分類的交易，須驗證 manual_override 仍被尊重。
        """
        from sqlalchemy import select as sa_select

        from ccas.classifier.job import run_reclassify_job

        db_session.add_all(
            [
                Category(keyword="星巴克", category="餐飲"),
                Category(keyword="購物-key", category="購物"),
            ]
        )
        await db_session.commit()
        purchase_cat = (
            await db_session.execute(
                sa_select(Category).where(Category.category == "購物")
            )
        ).scalar_one()

        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=200,
            due_date=date(2026, 4, 15),
        )
        db_session.add(bill)
        await db_session.flush()
        txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="星巴克",
            amount=200,
            category="餐飲",  # 已分類
        )
        db_session.add(txn)
        await db_session.commit()
        await db_session.refresh(txn)

        # 編輯為「購物」
        resp = await client.put(
            f"/api/transactions/{txn.id}",
            headers=auth_headers(),
            json={"category_id": purchase_cat.id},
        )
        assert resp.status_code == 200
        await db_session.refresh(txn)
        assert txn.category == "購物"
        assert txn.manual_category_override is True

        # 連跑 5 次 reclassify（fetch_all_transactions 會真正撈到這筆）
        for _ in range(5):
            summary = await run_reclassify_job(db_session)
            # manual_override_count 應該 ≥1（即此筆）
            assert summary.manual_override_count >= 1
        await db_session.refresh(txn)
        assert txn.category == "購物"
        assert txn.manual_category_override is True
