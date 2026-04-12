"""Shared fixtures for parser integration tests."""

from pathlib import Path

import pytest

_CJK_FONT_CANDIDATES = [
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
]


@pytest.fixture
def cjk_font_path() -> Path:
    """Resolve a CJK font path, skipping if none available."""
    for candidate in _CJK_FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    pytest.skip("CJK font not available")
