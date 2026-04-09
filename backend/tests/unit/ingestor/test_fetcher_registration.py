"""Smoke test: importing fetcher package populates the registry."""

from __future__ import annotations


def test_fubon_registered_via_package_import() -> None:
    """Package-level import must trigger bank fetcher registration."""
    from ccas.ingestor.fetcher import fetcher_registry

    fetcher = fetcher_registry.get("FUBON")
    assert fetcher is not None
    assert fetcher.bank_code == "FUBON"
