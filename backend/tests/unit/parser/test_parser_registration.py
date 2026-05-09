"""Smoke test: all supported bank parsers register on import."""

from __future__ import annotations

import importlib
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
