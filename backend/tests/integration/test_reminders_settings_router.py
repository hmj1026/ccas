"""Integration tests for ``/api/reminders/*`` settings endpoints.

bills-management-and-insights §5.5：CRUD settings + test push 端點覆蓋。
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import (
    BankConfig,
    Bill,
    ReminderChannel,
    ReminderSetting,
)
from tests.integration.conftest import auth_headers


async def _seed_bill(
    session: AsyncSession,
    *,
    bank_code: str = "CTBC",
    billing_month: str = "2026-05",
    days_until_due: int = 5,
) -> Bill:
    bank = BankConfig(
        bank_code=bank_code,
        bank_name=f"{bank_code}-name",
        gmail_filter=f"from:{bank_code.lower()}",
    )
    session.add(bank)
    bill = Bill(
        bank_code=bank_code,
        billing_month=billing_month,
        total_amount=12345,
        due_date=date.today() + timedelta(days=days_until_due),
        is_paid=False,
    )
    session.add(bill)
    await session.commit()
    await session.refresh(bill)
    return bill


class TestListReminderSettings:
    async def test_empty_state_when_no_bills(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get("/api/reminders/settings", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_lists_unpaid_bills_with_default_settings(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)

        resp = await client.get("/api/reminders/settings", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["bill_id"] == bill.id
        assert data[0]["bank_code"] == "CTBC"
        assert data[0]["bank_name"] == "CTBC-name"
        assert data[0]["enabled"] is True
        assert data[0]["days_before"] == [3, 1]
        assert data[0]["channel"] == "telegram"
        assert data[0]["has_setting"] is False

    async def test_lists_persisted_setting(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)
        db_session.add(
            ReminderSetting(
                bill_id=bill.id,
                enabled=False,
                days_before=[7, 1],
                channel=ReminderChannel.BOTH,
            )
        )
        await db_session.commit()

        resp = await client.get("/api/reminders/settings", headers=auth_headers())
        data = resp.json()["data"]
        assert data[0]["enabled"] is False
        assert data[0]["days_before"] == [7, 1]
        assert data[0]["channel"] == "both"
        assert data[0]["has_setting"] is True


class TestUpdateReminderSetting:
    async def test_creates_setting_when_absent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)

        resp = await client.put(
            f"/api/reminders/{bill.id}/settings",
            json={"enabled": False, "days_before": [5], "channel": "ui_banner"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["enabled"] is False
        assert resp.json()["data"]["days_before"] == [5]
        assert resp.json()["data"]["channel"] == "ui_banner"

        # DB 已寫入
        stmt = select(ReminderSetting).where(ReminderSetting.bill_id == bill.id)
        row = (await db_session.execute(stmt)).scalar_one()
        assert row.enabled is False
        assert row.days_before == [5]

    async def test_partial_update(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)
        db_session.add(
            ReminderSetting(
                bill_id=bill.id,
                enabled=True,
                days_before=[3, 1],
                channel=ReminderChannel.TELEGRAM,
            )
        )
        await db_session.commit()

        resp = await client.put(
            f"/api/reminders/{bill.id}/settings",
            json={"enabled": False},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is False
        assert resp.json()["data"]["days_before"] == [3, 1]
        assert resp.json()["data"]["channel"] == "telegram"

    async def test_404_when_bill_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.put(
            "/api/reminders/9999/settings",
            json={"enabled": False},
            headers=auth_headers(),
        )
        assert resp.status_code == 404

    async def test_422_invalid_days_before(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)
        resp = await client.put(
            f"/api/reminders/{bill.id}/settings",
            json={"days_before": [0, -1]},
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    async def test_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)
        resp = await client.put(
            f"/api/reminders/{bill.id}/settings",
            json={"enabled": False},
        )
        assert resp.status_code in (401, 403)


class TestPushReminderTest:
    async def test_pushes_via_telegram_when_channel_telegram(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)

        with patch(
            "ccas.api.routers.reminders_settings.send_message",
            new=AsyncMock(return_value=None),
        ) as mock_send:
            resp = await client.post(
                f"/api/reminders/{bill.id}/test",
                headers=auth_headers(),
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["sent"] is True
        assert resp.json()["data"]["channel"] == "telegram"
        assert mock_send.await_count == 1

    async def test_skips_send_for_ui_banner_channel(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bill = await _seed_bill(db_session)
        db_session.add(
            ReminderSetting(
                bill_id=bill.id,
                enabled=True,
                days_before=[3, 1],
                channel=ReminderChannel.UI_BANNER,
            )
        )
        await db_session.commit()

        with patch(
            "ccas.api.routers.reminders_settings.send_message",
            new=AsyncMock(return_value=None),
        ) as mock_send:
            resp = await client.post(
                f"/api/reminders/{bill.id}/test",
                headers=auth_headers(),
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["channel"] == "ui_banner"
        assert resp.json()["data"]["sent"] is False
        assert mock_send.await_count == 0

    async def test_404_when_bill_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.post(
            "/api/reminders/9999/test",
            headers=auth_headers(),
        )
        assert resp.status_code == 404
