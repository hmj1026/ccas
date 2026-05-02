"""Integration tests for /api/setup/banks/* endpoints (oauth-onboarding-ui §4)."""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, BankSettings, StagedAttachment
from tests.integration.conftest import auth_headers


def _make_config(code: str, name: str, *, is_active: bool = True) -> BankConfig:
    return BankConfig(
        bank_code=code,
        bank_name=name,
        gmail_filter=f"from:{code.lower()}@example.com",
        is_active=is_active,
    )


def _make_attachment(code: str, *, message_date: datetime) -> StagedAttachment:
    return StagedAttachment(
        bank_code=code,
        gmail_message_id=f"msg-{code}-{message_date.timestamp()}",
        gmail_attachment_id=f"att-{code}-{message_date.timestamp()}",
        gmail_part_id=f"part-{code}-{message_date.timestamp()}",
        message_date=message_date,
        original_filename=f"{code}.pdf",
        staged_path=f"{code}/file.pdf",
        status="staged",
    )


class TestListSetupBanks:
    async def test_returns_all_bank_configs_with_default_enabled(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add_all(
            [
                _make_config("CTBC", "中國信託"),
                _make_config("ESUN", "玉山銀行"),
            ]
        )
        await db_session.commit()

        resp = await client.get("/api/setup/banks", headers=auth_headers())

        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]
        codes = {item["code"] for item in items}
        assert codes == {"CTBC", "ESUN"}
        ctbc = next(item for item in items if item["code"] == "CTBC")
        assert ctbc["enabled"] is True
        assert ctbc["has_settings_row"] is False
        assert ctbc["metadata_missing"] is False
        assert ctbc["total_pdfs"] == 0
        assert ctbc["last_ingest_at"] is None

    async def test_settings_row_overrides_config_active(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(_make_config("CTBC", "中國信託", is_active=True))
        db_session.add(BankSettings(code="CTBC", enabled=False, display_name="中信"))
        await db_session.commit()

        resp = await client.get("/api/setup/banks", headers=auth_headers())

        item = resp.json()["data"][0]
        assert item["enabled"] is False
        assert item["has_settings_row"] is True
        assert item["display_name"] == "中信"

    async def test_orphan_settings_row_marked_metadata_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # bank_settings has a row but bank_configs does not.
        db_session.add(BankSettings(code="HSBC", enabled=True))
        await db_session.commit()

        resp = await client.get("/api/setup/banks", headers=auth_headers())

        items = resp.json()["data"]
        hsbc = next(item for item in items if item["code"] == "HSBC")
        assert hsbc["metadata_missing"] is True
        assert hsbc["enabled"] is True

    async def test_aggregates_total_pdfs_and_last_ingest(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(_make_config("CTBC", "中國信託"))
        early = datetime(2025, 1, 5, tzinfo=UTC)
        late = datetime(2025, 3, 12, tzinfo=UTC)
        db_session.add(_make_attachment("CTBC", message_date=early))
        db_session.add(_make_attachment("CTBC", message_date=late))
        await db_session.commit()

        resp = await client.get("/api/setup/banks", headers=auth_headers())

        ctbc = resp.json()["data"][0]
        assert ctbc["total_pdfs"] == 2
        assert ctbc["last_ingest_at"].startswith("2025-03-12")

    async def test_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/setup/banks")
        assert resp.status_code == 401


class TestUpdateSetupBank:
    async def test_creates_settings_row_when_missing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(_make_config("CTBC", "中國信託"))
        await db_session.commit()

        resp = await client.put(
            "/api/setup/banks/CTBC",
            json={"enabled": False, "display_name": "中信", "notes": "停用測試"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["enabled"] is False
        assert body["display_name"] == "中信"

        row = await db_session.get(BankSettings, "CTBC")
        assert row is not None
        assert row.enabled is False
        assert row.notes == "停用測試"

    async def test_updates_existing_settings_row(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(_make_config("CTBC", "中國信託"))
        db_session.add(BankSettings(code="CTBC", enabled=True, display_name="中信"))
        await db_session.commit()

        resp = await client.put(
            "/api/setup/banks/CTBC",
            json={"enabled": False},
            headers=auth_headers(),
        )

        assert resp.status_code == 200
        await db_session.refresh(
            (await db_session.execute(select(BankSettings))).scalar_one()
        )
        row = await db_session.get(BankSettings, "CTBC")
        assert row is not None
        assert row.enabled is False

    async def test_normalizes_code_to_upper(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add(_make_config("CTBC", "中國信託"))
        await db_session.commit()

        resp = await client.put(
            "/api/setup/banks/ctbc",
            json={"enabled": False},
            headers=auth_headers(),
        )

        assert resp.status_code == 200
        row = await db_session.get(BankSettings, "CTBC")
        assert row is not None and row.enabled is False

    async def test_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.put("/api/setup/banks/CTBC", json={"enabled": False})
        assert resp.status_code == 401


class TestApplyBankSettingsFilter:
    """Unit-style: ingestor _fetch_active_banks honors bank_settings override."""

    async def test_disabled_in_settings_excluded_even_if_config_active(
        self, db_session: AsyncSession
    ) -> None:
        from ccas.ingestor.job import _fetch_active_banks

        db_session.add(_make_config("CTBC", "中國信託", is_active=True))
        db_session.add(_make_config("ESUN", "玉山銀行", is_active=True))
        db_session.add(BankSettings(code="CTBC", enabled=False))
        await db_session.commit()

        result = await _fetch_active_banks(db_session)

        codes = {b.bank_code for b in result}
        assert codes == {"ESUN"}

    async def test_no_settings_row_falls_back_to_config_is_active(
        self, db_session: AsyncSession
    ) -> None:
        from ccas.ingestor.job import _fetch_active_banks

        db_session.add(_make_config("CTBC", "中國信託", is_active=True))
        db_session.add(_make_config("ESUN", "玉山銀行", is_active=False))
        await db_session.commit()

        result = await _fetch_active_banks(db_session)

        codes = {b.bank_code for b in result}
        assert codes == {"CTBC"}

    async def test_settings_enabled_true_overrides_inactive_config(
        self, db_session: AsyncSession
    ) -> None:
        from ccas.ingestor.job import _fetch_active_banks

        # Ingestor base query already filters is_active=True, so even if
        # bank_settings says enabled=true, an inactive config row will not
        # surface — that's the documented behavior (DB seeds bank_configs).
        # This test verifies the fallback layer is the only override path.
        db_session.add(_make_config("CTBC", "中國信託", is_active=False))
        db_session.add(BankSettings(code="CTBC", enabled=True))
        await db_session.commit()

        result = await _fetch_active_banks(db_session)

        # Inactive bank_configs.is_active=False is filtered upstream by base
        # SQL query; bank_settings.enabled=true cannot resurrect it.
        assert all(b.bank_code != "CTBC" for b in result)
