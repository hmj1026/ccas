"""Integration tests for ``/api/rules/*`` endpoints.

bills-management-and-insights §4.7-§4.8：CRUD + 即時測試端點 + priority 排序
+ enabled filter 覆蓋。
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.routers.rules import _integrity_error_to_http
from ccas.storage.models import (
    Category,
    PatternType,
    UserClassificationRule,
)
from tests.integration.conftest import auth_headers


async def _seed_category(session: AsyncSession, name: str) -> Category:
    cat = Category(keyword=f"{name}-key", category=name)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


class TestListRules:
    async def test_empty_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get("/api/rules", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_orders_by_priority_desc_then_id_asc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "餐飲")
        db_session.add_all(
            [
                UserClassificationRule(
                    pattern="low",
                    pattern_type=PatternType.KEYWORD,
                    category_id=cat.id,
                    priority=1,
                    enabled=True,
                ),
                UserClassificationRule(
                    pattern="high",
                    pattern_type=PatternType.KEYWORD,
                    category_id=cat.id,
                    priority=10,
                    enabled=True,
                ),
                UserClassificationRule(
                    pattern="mid",
                    pattern_type=PatternType.KEYWORD,
                    category_id=cat.id,
                    priority=5,
                    enabled=True,
                ),
            ]
        )
        await db_session.commit()

        resp = await client.get("/api/rules", headers=auth_headers())
        items = resp.json()["data"]
        assert [item["pattern"] for item in items] == ["high", "mid", "low"]
        assert items[0]["category_name"] == "餐飲"

    async def test_enabled_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "X")
        db_session.add_all(
            [
                UserClassificationRule(
                    pattern="A",
                    pattern_type=PatternType.KEYWORD,
                    category_id=cat.id,
                    enabled=True,
                ),
                UserClassificationRule(
                    pattern="B",
                    pattern_type=PatternType.KEYWORD,
                    category_id=cat.id,
                    enabled=False,
                ),
            ]
        )
        await db_session.commit()

        resp_enabled = await client.get(
            "/api/rules?enabled=true", headers=auth_headers()
        )
        assert [r["pattern"] for r in resp_enabled.json()["data"]] == ["A"]

        resp_disabled = await client.get(
            "/api/rules?enabled=false", headers=auth_headers()
        )
        assert [r["pattern"] for r in resp_disabled.json()["data"]] == ["B"]

    async def test_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get("/api/rules")
        assert resp.status_code == 401


class TestCreateRule:
    async def test_create_success(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "餐飲")
        resp = await client.post(
            "/api/rules",
            headers=auth_headers(),
            json={
                "pattern": "星巴克",
                "pattern_type": "keyword",
                "category_id": cat.id,
                "priority": 10,
                "enabled": True,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["pattern"] == "星巴克"
        assert body["category_name"] == "餐飲"
        assert body["priority"] == 10

    async def test_create_with_invalid_category_id(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/rules",
            headers=auth_headers(),
            json={
                "pattern": "x",
                "pattern_type": "keyword",
                "category_id": 9999,
            },
        )
        assert resp.status_code == 422

    async def test_create_validates_min_length_pattern(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "X")
        resp = await client.post(
            "/api/rules",
            headers=auth_headers(),
            json={
                "pattern": "",
                "pattern_type": "keyword",
                "category_id": cat.id,
            },
        )
        assert resp.status_code == 422


class TestUpdateRule:
    async def test_update_partial_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "餐飲")
        rule = UserClassificationRule(
            pattern="星巴克",
            pattern_type=PatternType.KEYWORD,
            category_id=cat.id,
            priority=5,
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.put(
            f"/api/rules/{rule.id}",
            headers=auth_headers(),
            json={"priority": 99, "enabled": False},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["priority"] == 99
        assert body["enabled"] is False
        assert body["pattern"] == "星巴克"  # 未動

    async def test_update_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.put(
            "/api/rules/9999",
            headers=auth_headers(),
            json={"priority": 1},
        )
        assert resp.status_code == 404

    async def test_update_invalid_category_id_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "X")
        rule = UserClassificationRule(
            pattern="x",
            pattern_type=PatternType.KEYWORD,
            category_id=cat.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.put(
            f"/api/rules/{rule.id}",
            headers=auth_headers(),
            json={"category_id": 9999},
        )
        assert resp.status_code == 422


class TestDeleteRule:
    async def test_delete_existing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        cat = await _seed_category(db_session, "X")
        rule = UserClassificationRule(
            pattern="x",
            pattern_type=PatternType.KEYWORD,
            category_id=cat.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.delete(f"/api/rules/{rule.id}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_id"] == rule.id

        # 確認 DB 已無此 row
        remaining = (
            (await db_session.execute(select(UserClassificationRule))).scalars().all()
        )
        assert remaining == []

    async def test_delete_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.delete("/api/rules/9999", headers=auth_headers())
        assert resp.status_code == 404


class TestRuleTestEndpoint:
    async def test_keyword_match(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/rules/test",
            headers=auth_headers(),
            json={
                "pattern": "星巴克",
                "pattern_type": "keyword",
                "sample_text": "星巴克信義店",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["matches"] is True

    async def test_keyword_no_match(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/rules/test",
            headers=auth_headers(),
            json={
                "pattern": "Louisa",
                "pattern_type": "keyword",
                "sample_text": "Starbucks",
            },
        )
        assert resp.json()["data"]["matches"] is False

    async def test_regex_match(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/rules/test",
            headers=auth_headers(),
            json={
                "pattern": r"^7-?eleven",
                "pattern_type": "regex",
                "sample_text": "7-Eleven 中正店",
            },
        )
        assert resp.json()["data"]["matches"] is True

    async def test_regex_compile_error_returns_no_match(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/rules/test",
            headers=auth_headers(),
            json={
                "pattern": "[unclosed",
                "pattern_type": "regex",
                "sample_text": "test",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["matches"] is False

    async def test_test_endpoint_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/rules/test",
            json={"pattern": "x", "pattern_type": "keyword", "sample_text": "x"},
        )
        assert resp.status_code == 401


class TestIntegrityErrorMapping:
    """``_integrity_error_to_http`` 把 DB 完整性錯誤轉成友善 422，不洩漏 schema。

    說明：``classification_rules.pattern`` 目前沒有 UNIQUE 約束（見
    ``5f9d4a7b3c8e`` migration 的 ``CREATE INDEX``，非 ``UNIQUE``），且 FK
    違反在 ``create_rule`` 進 INSERT 前已由 ``_resolve_category_name`` 攔下，
    因此 IntegrityError 路徑無法用真實端點觸發。改為直接單元測映射函式，
    驗證它回 422、回友善訊息、且**不**把 column 名洩漏給 client。
    """

    @staticmethod
    def _make_integrity_error(orig_message: str) -> IntegrityError:
        return IntegrityError(
            statement="INSERT INTO classification_rules ...",
            params=None,
            orig=Exception(orig_message),
        )

    def test_unique_violation_maps_to_friendly_message_without_leak(self) -> None:
        exc = self._make_integrity_error(
            "UNIQUE constraint failed: classification_rules.pattern"
        )
        http_exc = _integrity_error_to_http(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail == "相同 pattern 的規則已存在"
        # The raw column name must NOT leak to the client.
        assert "classification_rules" not in http_exc.detail
        assert "constraint" not in http_exc.detail.lower()

    def test_foreign_key_violation_maps_to_friendly_message(self) -> None:
        exc = self._make_integrity_error("FOREIGN KEY constraint failed")
        http_exc = _integrity_error_to_http(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail == "指定的 category_id 不存在"

    def test_other_integrity_error_maps_to_generic_message(self) -> None:
        exc = self._make_integrity_error("NOT NULL constraint failed: foo.bar")
        http_exc = _integrity_error_to_http(exc)
        assert http_exc.status_code == 422
        assert http_exc.detail == "資料完整性錯誤，請確認輸入值"
        assert "foo.bar" not in http_exc.detail
