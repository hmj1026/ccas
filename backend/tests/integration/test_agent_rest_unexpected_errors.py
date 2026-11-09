"""Agent 支撐的 REST 路由：非預期失敗與 MCP / CLI 使用同一個公開投影。

非預期失敗無法以真實輸入穩定觸發，故在 router 的 service 匯入點替換成會拋錯的
函式；斷言的是對外回應（route class 這個 seam），不是內部呼叫。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import BaseModel

from ccas.api.routers import bills as bills_router
from tests.integration.conftest import auth_headers


class _Model(BaseModel):
    value: int


async def _raise_runtime(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("SELECT * FROM bank_secrets WHERE password='hunter2'")


async def _raise_validation(*_args: object, **_kwargs: object) -> None:
    _Model.model_validate({"value": "not-an-int"})


@pytest.mark.asyncio
async def test_unexpected_failure_returns_query_failed_envelope(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bills_router, "service_list_bills", _raise_runtime)

    response = await client.get("/api/bills", headers=auth_headers())

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "message": "Agent query failed; manual review and check required.",
        "data": None,
    }
    assert "hunter2" not in response.text


@pytest.mark.asyncio
async def test_validation_failure_returns_invalid_data_envelope(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bills_router, "service_list_bills", _raise_validation)

    response = await client.get("/api/bills", headers=auth_headers())

    assert response.status_code == 500
    assert response.json()["message"] == (
        "Database contains invalid data; human review required."
    )
    assert "not-an-int" not in response.text
