"""Tests for release version consistency across runtime surfaces."""

from __future__ import annotations

from importlib.metadata import version as package_version

from ccas import __version__
from ccas.api.app import create_app
from ccas.mcp import __version__ as mcp_version


def test_runtime_surfaces_expose_the_released_package_version() -> None:
    app = create_app()

    assert __version__ == "0.10.1"
    assert package_version("ccas") == __version__
    assert mcp_version == __version__
    assert app.version == __version__
