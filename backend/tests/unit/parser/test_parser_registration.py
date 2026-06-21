"""Smoke test: all supported bank parsers register on import."""

from __future__ import annotations

import importlib
import re
import sys

import pytest

from ccas.parser.registry import registry

_EXPECTED_BANK_CODES = ("CATHAY", "CTBC", "ESUN", "FUBON", "SINOPAC", "TAISHIN", "UBOT")

_BANK_MODULES = [
    f"ccas.parser.banks.{code.lower()}_v1" for code in _EXPECTED_BANK_CODES
]


def _reload_all_bank_modules() -> None:
    """Reload every bank parser submodule to re-trigger registration.

    The autouse ``_reset_registry`` fixture clears the registry before each
    test.  A plain ``importlib.reload(ccas.parser.banks)`` only re-executes
    the package ``__init__`` -- already-cached submodules are not re-run.
    We must reload each submodule explicitly.
    """
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
