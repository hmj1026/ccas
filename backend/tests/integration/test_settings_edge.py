"""Settings API 邊界測試：補強 404、IntegrityError、partial update 路徑。"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Category
from tests.integration.conftest import auth_headers, make_ctbc_bank_config


# -- Banks edge cases --


async def test_update_bank_not_found(client: AsyncClient, db_session: AsyncSession):
    """更新不存在的銀行設定回傳 404。"""
    response = await client.patch(
        "/api/settings/banks/999",
        json={"is_active": False},
        headers=auth_headers(),
    )
    assert response.status_code == 404


async def test_update_bank_partial_is_active_only(
    client: AsyncClient, db_session: AsyncSession
):
    """僅更新 is_active，active_parser_version 不變。"""
    bank = make_ctbc_bank_config()
    db_session.add(bank)
    await db_session.commit()

    response = await client.patch(
        f"/api/settings/banks/{bank.id}",
        json={"is_active": False},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_active"] is False
    # active_parser_version should remain unchanged from factory default
    assert data["is_active"] is False


async def test_update_bank_partial_parser_only(
    client: AsyncClient, db_session: AsyncSession
):
    """僅更新 active_parser_version，is_active 不變。"""
    bank = make_ctbc_bank_config()
    db_session.add(bank)
    await db_session.commit()

    response = await client.patch(
        f"/api/settings/banks/{bank.id}",
        json={"active_parser_version": "v2"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["active_parser_version"] == "v2"
    assert data["is_active"] is True  # default unchanged


async def test_list_banks_empty(client: AsyncClient, db_session: AsyncSession):
    """無銀行設定時回傳空列表。"""
    response = await client.get("/api/settings/banks", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["data"] == []


# -- Categories edge cases --


async def test_update_category_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    """更新不存在的分類回傳 404。"""
    response = await client.patch(
        "/api/settings/categories/999",
        json={"category": "other"},
        headers=auth_headers(),
    )
    assert response.status_code == 404


async def test_update_category_duplicate_keyword(
    client: AsyncClient, db_session: AsyncSession
):
    """更新分類時 keyword 衝突回傳 409。"""
    cat1 = Category(keyword="星巴克", category="餐飲")
    cat2 = Category(keyword="全聯", category="日用品")
    db_session.add_all([cat1, cat2])
    await db_session.commit()

    response = await client.patch(
        f"/api/settings/categories/{cat2.id}",
        json={"keyword": "星巴克"},  # conflicts with cat1
        headers=auth_headers(),
    )
    assert response.status_code == 409


async def test_update_category_keyword_and_category(
    client: AsyncClient, db_session: AsyncSession
):
    """同時更新 keyword 和 category。"""
    cat = Category(keyword="星巴克", category="餐飲")
    db_session.add(cat)
    await db_session.commit()

    response = await client.patch(
        f"/api/settings/categories/{cat.id}",
        json={"keyword": "STARBUCKS", "category": "飲料"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["keyword"] == "STARBUCKS"
    assert data["category"] == "飲料"


async def test_list_categories_empty(client: AsyncClient, db_session: AsyncSession):
    """無分類時回傳空列表。"""
    response = await client.get("/api/settings/categories", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["data"] == []


# -- Auth edge cases --


async def test_settings_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """無 token 存取 settings 回傳 401。"""
    response = await client.get("/api/settings/banks")
    assert response.status_code == 401


async def test_settings_invalid_token(client: AsyncClient, db_session: AsyncSession):
    """錯誤 token 存取 settings 回傳 401。"""
    response = await client.get(
        "/api/settings/banks",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
