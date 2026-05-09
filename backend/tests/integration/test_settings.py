"""Settings API 測試（銀行設定 CRUD、分類關鍵字 CRUD）。"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Category
from tests.integration.conftest import auth_headers, make_ctbc_bank_config

# -- Banks --


async def test_list_banks(client: AsyncClient, db_session: AsyncSession):
    """取得銀行設定清單。"""
    bank = BankConfig(
        bank_code="CTBC",
        bank_name="中國信託",
        gmail_filter="from:ctbc",
        pdf_password_rule="ID+birthday",
    )
    db_session.add(bank)
    await db_session.commit()

    response = await client.get("/api/settings/banks", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "CTBC"
    # 不應包含 pdf_password_rule
    assert "pdf_password_rule" not in data[0]


async def test_create_bank(client: AsyncClient, db_session: AsyncSession):
    """新增銀行設定。"""
    response = await client.post(
        "/api/settings/banks",
        json={
            "bank_code": "ESUN",
            "bank_name": "玉山銀行",
            "gmail_filter": "from:esun",
        },
        headers=auth_headers(),
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["bank_code"] == "ESUN"
    assert data["is_active"] is True


async def test_create_bank_duplicate(client: AsyncClient, db_session: AsyncSession):
    """重複銀行代碼回傳 409。"""
    bank = make_ctbc_bank_config()
    db_session.add(bank)
    await db_session.commit()

    response = await client.post(
        "/api/settings/banks",
        json={
            "bank_code": "CTBC",
            "bank_name": "中國信託",
            "gmail_filter": "from:ctbc",
        },
        headers=auth_headers(),
    )
    assert response.status_code == 409


async def test_update_bank(client: AsyncClient, db_session: AsyncSession):
    """更新銀行設定。"""
    bank = make_ctbc_bank_config()
    db_session.add(bank)
    await db_session.commit()

    response = await client.patch(
        f"/api/settings/banks/{bank.id}",
        json={"is_active": False, "active_parser_version": "v2"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_active"] is False
    assert data["active_parser_version"] == "v2"


# -- Categories --


async def test_list_categories(client: AsyncClient, db_session: AsyncSession):
    """取得分類關鍵字清單。"""
    cat = Category(keyword="星巴克", category="餐飲")
    db_session.add(cat)
    await db_session.commit()

    response = await client.get("/api/settings/categories", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["keyword"] == "星巴克"


async def test_create_category(client: AsyncClient, db_session: AsyncSession):
    """新增分類關鍵字。"""
    response = await client.post(
        "/api/settings/categories",
        json={"keyword": "全聯", "category": "日用"},
        headers=auth_headers(),
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["keyword"] == "全聯"
    assert data["category"] == "日用"


async def test_create_category_duplicate(client: AsyncClient, db_session: AsyncSession):
    """重複關鍵字回傳 409。"""
    cat = Category(keyword="星巴克", category="餐飲")
    db_session.add(cat)
    await db_session.commit()

    response = await client.post(
        "/api/settings/categories",
        json={"keyword": "星巴克", "category": "飲料"},
        headers=auth_headers(),
    )
    assert response.status_code == 409


async def test_update_category(client: AsyncClient, db_session: AsyncSession):
    """更新分類關鍵字。"""
    cat = Category(keyword="星巴克", category="餐飲")
    db_session.add(cat)
    await db_session.commit()

    response = await client.patch(
        f"/api/settings/categories/{cat.id}",
        json={"category": "飲料"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["data"]["category"] == "飲料"


async def test_delete_category(client: AsyncClient, db_session: AsyncSession):
    """刪除分類關鍵字。"""
    cat = Category(keyword="星巴克", category="餐飲")
    db_session.add(cat)
    await db_session.commit()

    response = await client.delete(
        f"/api/settings/categories/{cat.id}", headers=auth_headers()
    )
    assert response.status_code == 204

    # 確認已刪除
    response = await client.get("/api/settings/categories", headers=auth_headers())
    assert len(response.json()["data"]) == 0


async def test_delete_category_not_found(client: AsyncClient, db_session: AsyncSession):
    """刪除不存在的分類回傳 404。"""
    response = await client.delete(
        "/api/settings/categories/999", headers=auth_headers()
    )
    assert response.status_code == 404
