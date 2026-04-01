"""YAML 銀行設定載入與同步工具測試。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ccas.tools.bank_configs import (
    BankConfigSpec,
    BankConfigValidationError,
    load_bank_config_specs,
    load_bank_registry,
    main,
    sync_bank_configs,
)


def _make_mock_session(rows: list[object]) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session.execute.return_value = execute_result
    return session


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "bank-code-registry.yaml"
    path.write_text(
        """
banks:
  - bank_code: CTBC
    bank_name: 中國信託
    supported: false
  - bank_code: ESUN
    bank_name: 玉山銀行
    supported: false
""".strip()
    )
    return path


def test_load_bank_registry_returns_lookup(registry_file: Path):
    registry = load_bank_registry(registry_file)

    assert sorted(registry) == ["CTBC", "ESUN"]
    assert registry["CTBC"].bank_name == "中國信託"


def test_load_bank_config_specs_normalizes_and_defaults(
    tmp_path: Path, registry_file: Path
):
    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        """
banks:
  - bank_code: ctbc
    gmail_filter: "from:service@ctbcbank.com subject:信用卡"
""".strip()
    )

    specs = load_bank_config_specs(config_file, registry_file)

    assert len(specs) == 1
    assert specs[0].bank_code == "CTBC"
    assert specs[0].bank_name == "中國信託"
    assert specs[0].active_parser_version == "v1"
    assert specs[0].is_active is True


def test_load_bank_config_specs_rejects_unknown_bank_code(
    tmp_path: Path, registry_file: Path
):
    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        """
banks:
  - bank_code: UNKNOWN
    gmail_filter: "from:unknown@example.com"
""".strip()
    )

    with pytest.raises(BankConfigValidationError) as exc:
        load_bank_config_specs(config_file, registry_file)

    message = str(exc.value)
    assert "UNKNOWN" in message
    assert "bank-code-registry.yaml" in message


def test_load_bank_config_specs_rejects_duplicate_bank_code(
    tmp_path: Path, registry_file: Path
):
    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        """
banks:
  - bank_code: CTBC
    gmail_filter: "from:first@example.com"
  - bank_code: ctbc
    gmail_filter: "from:second@example.com"
""".strip()
    )

    with pytest.raises(BankConfigValidationError, match="重複"):
        load_bank_config_specs(config_file, registry_file)


def test_load_bank_config_specs_requires_gmail_filter(
    tmp_path: Path, registry_file: Path
):
    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        """
banks:
  - bank_code: CTBC
    gmail_filter: ""
""".strip()
    )

    with pytest.raises(BankConfigValidationError, match="gmail_filter"):
        load_bank_config_specs(config_file, registry_file)


@pytest.mark.asyncio
async def test_sync_bank_configs_upserts_existing_rows(
    tmp_path: Path,
    registry_file: Path,
):
    existing_row = SimpleNamespace(
        bank_code="CTBC",
        bank_name="舊名稱",
        gmail_filter="from:old@example.com",
        active_parser_version="v0",
        is_active=False,
    )
    session = _make_mock_session([existing_row])

    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        """
banks:
  - bank_code: CTBC
    gmail_filter: "from:new@example.com"
    active_parser_version: v2
    is_active: true
  - bank_code: ESUN
    gmail_filter: "from:esun@example.com"
    is_active: false
""".strip()
    )

    specs = load_bank_config_specs(config_file, registry_file)
    summary = await sync_bank_configs(session, specs, apply_changes=True)

    assert summary.created == 1
    assert summary.updated == 1
    assert summary.unchanged == 0
    assert existing_row.bank_name == "中國信託"
    assert existing_row.gmail_filter == "from:new@example.com"
    assert existing_row.active_parser_version == "v2"
    assert existing_row.is_active is True
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_bank_configs_dry_run_does_not_persist(
    tmp_path: Path,
    registry_file: Path,
):
    session = _make_mock_session([])

    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        """
banks:
  - bank_code: CTBC
    gmail_filter: "from:ctbc@example.com"
""".strip()
    )

    specs = load_bank_config_specs(config_file, registry_file)
    summary = await sync_bank_configs(session, specs, apply_changes=False)

    assert summary.created == 1
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


# -- _load_yaml_mapping edge cases (tested indirectly via load_bank_registry) --


def test_registry_file_not_found(tmp_path: Path):
    with pytest.raises(BankConfigValidationError, match="找不到"):
        load_bank_registry(tmp_path / "nonexistent.yaml")


def test_registry_invalid_yaml(tmp_path: Path):
    path = tmp_path / "broken.yaml"
    path.write_text("{[broken")

    with pytest.raises(BankConfigValidationError, match="不是合法 YAML"):
        load_bank_registry(path)


def test_registry_non_dict_toplevel(tmp_path: Path):
    path = tmp_path / "list.yaml"
    path.write_text("- item1\n- item2")

    with pytest.raises(BankConfigValidationError, match="頂層必須是物件"):
        load_bank_registry(path)


# -- load_bank_registry edge cases --


def test_registry_empty_banks(tmp_path: Path):
    path = tmp_path / "empty.yaml"
    path.write_text("banks: []")

    with pytest.raises(BankConfigValidationError, match="非空的 banks"):
        load_bank_registry(path)


def test_registry_non_list_banks(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text('banks: "not a list"')

    with pytest.raises(BankConfigValidationError, match="非空的 banks"):
        load_bank_registry(path)


def test_registry_non_dict_row(tmp_path: Path):
    path = tmp_path / "bad-row.yaml"
    path.write_text("banks:\n  - just a string")

    with pytest.raises(BankConfigValidationError, match="必須是物件"):
        load_bank_registry(path)


def test_registry_missing_required_fields(tmp_path: Path):
    path = tmp_path / "missing.yaml"
    path.write_text("banks:\n  - bank_code: CTBC")

    with pytest.raises(BankConfigValidationError, match="缺少 bank_code 或 bank_name"):
        load_bank_registry(path)


def test_registry_duplicate_bank_code(tmp_path: Path):
    path = tmp_path / "dup.yaml"
    path.write_text(
        "banks:\n"
        "  - bank_code: CTBC\n"
        "    bank_name: 中國信託\n"
        "  - bank_code: CTBC\n"
        "    bank_name: 重複\n"
    )

    with pytest.raises(BankConfigValidationError, match="重複 bank_code"):
        load_bank_registry(path)


# -- load_bank_config_specs edge cases --


def test_config_missing_bank_code_field(tmp_path: Path, registry_file: Path):
    config_file = tmp_path / "banks.yaml"
    config_file.write_text(
        'banks:\n  - gmail_filter: "from:x@example.com"'
    )

    with pytest.raises(BankConfigValidationError, match="缺少 bank_code"):
        load_bank_config_specs(config_file, registry_file)


# -- sync_bank_configs edge cases --


@pytest.mark.asyncio
async def test_sync_unchanged_row(registry_file: Path):
    existing_row = SimpleNamespace(
        bank_code="CTBC",
        bank_name="中國信託",
        gmail_filter="from:ctbc@example.com",
        active_parser_version="v1",
        is_active=True,
    )
    session = _make_mock_session([existing_row])

    specs = [
        BankConfigSpec(
            bank_code="CTBC",
            bank_name="中國信託",
            gmail_filter="from:ctbc@example.com",
            active_parser_version="v1",
            is_active=True,
        )
    ]
    summary = await sync_bank_configs(session, specs, apply_changes=True)

    assert summary.unchanged == 1
    assert summary.created == 0
    assert summary.updated == 0
    assert "UNCHANGED" in summary.actions[0]
    session.add.assert_not_called()


# -- main() CLI --


def test_main_returns_2_on_validation_error(tmp_path: Path):
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("{[broken")

    result = main([
        "--config", str(bad_config),
        "--registry", str(tmp_path / "nonexistent.yaml"),
    ])

    assert result == 2
