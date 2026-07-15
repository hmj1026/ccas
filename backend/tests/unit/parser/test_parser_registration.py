"""Smoke test: all supported bank parsers register on import."""

from __future__ import annotations

import importlib
import re
import subprocess
import sys

import pytest

from ccas.parser.registry import registry

_EXPECTED_BANK_CODES = ("CATHAY", "CTBC", "ESUN", "FUBON", "SINOPAC", "TAISHIN", "UBOT")

_BANK_MODULES = [
    f"ccas.parser.banks.{code.lower()}_v1" for code in _EXPECTED_BANK_CODES
]


def test_registry_import_does_not_discover_bank_modules() -> None:
    """Low-level consumers stay side-effect free until the assembly point runs."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import ccas.parser.registry; "
                "raise SystemExit(int('ccas.parser.banks' in sys.modules))"
            ),
        ],
        check=False,
    )
    assert result.returncode == 0


def _reload_all_bank_modules() -> None:
    """Reload every bank parser submodule to re-trigger registration.

    The autouse ``_reset_registry`` fixture clears the registry before each
    test.  A plain ``importlib.reload(ccas.parser.banks)`` only re-executes
    the package ``__init__`` -- already-cached submodules are not re-run.
    We must reload each submodule explicitly.
    """
    # Test-only registry reset means cached modules must be executed again.
    # Import the package first so the very first test also populates sys.modules;
    # production assembly remains exclusively build_parser_intake().
    importlib.import_module("ccas.parser.banks")
    for mod_name in _BANK_MODULES:
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])


@pytest.mark.parametrize("bank_code", _EXPECTED_BANK_CODES)
def test_parser_registered_for_bank(bank_code: str) -> None:
    """registry.resolve() must succeed for every supported bank code."""
    _reload_all_bank_modules()

    candidates = registry.resolve(bank_code)
    assert len(candidates) >= 1, f"No parser registered for {bank_code}"
    assert candidates[0].bank_code.upper() == bank_code


def test_dynamic_discovery_loads_every_expected_parser() -> None:
    """`banks/__init__` 動態探索須涵蓋全部預期 parser 模組（無漏載）。

    這是 import 清單改為 pkgutil 動態探索後的防漏網：若某個 ``*_v1.py``
    未被探索到（例如命名不符或 regex 漏掉），此斷言會紅燈。
    """
    import ccas.parser.banks as banks_pkg

    expected_v1 = {f"{code.lower()}_v1" for code in _EXPECTED_BANK_CODES}
    discovered = set(banks_pkg.DISCOVERED_PARSER_MODULES)

    missing = expected_v1 - discovered
    assert not missing, f"動態探索漏載 parser 模組: {sorted(missing)}"

    # 探索結果不得包含非 parser 的輔助子套件（如 ctbc/）；
    # 每個探索到的名稱都必須符合 `{bank_code}_v{N}` 命名契約。
    assert "ctbc" not in discovered
    for name in discovered:
        assert re.fullmatch(r"[a-z]+_v\d+", name), f"非預期的探索結果: {name}"


def test_explicit_assembly_registers_all_banks_without_consumer_imports() -> None:
    """組裝點契約：`build_parser_intake()` 自行確保七家銀行可解析。

    消費端（run_parse_job、測試）不得依賴先 import `ccas.parser.banks`
    的副作用順序；`ensure_discovered()` 需可重入且在 registry 被清空後
    仍能透過 module reload 恢復（本測試模擬 fresh-process 首次組裝）。
    """
    _reload_all_bank_modules()

    from ccas.parser.intake import build_parser_intake

    intake = build_parser_intake()
    intake2 = build_parser_intake()  # 再次組裝必須冪等、不重複註冊
    assert intake is not intake2

    for bank_code in _EXPECTED_BANK_CODES:
        candidates = intake.registry.resolve(bank_code)
        assert len(candidates) >= 1, f"assembly 後 {bank_code} 不可解析"
        versions = [c.version for c in candidates]
        assert len(versions) == len(set(versions)), f"{bank_code} 重複註冊: {versions}"
