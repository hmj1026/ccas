"""FubonFetcher manual-staging fallback tests.

Covers 5 scenarios per the spec:
1. Manual staging empty → FetchError with guidance
2. Filename matches billing month → exact pick + move
3. Single file without month → pick by mtime
4. Multiple files without month → FetchError
5. SPA failure + manual staging file → fallback succeeds
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ccas.config import Settings
from ccas.ingestor.fetcher.banks.fubon import FubonFetcher, flow
from ccas.ingestor.fetcher.base import FetchError

_SPA_HTML = """
<html><body>
<a href="https://fbmbill.taipeifubon.com.tw/abc123">
  <img src="https://fbmbill.taipeifubon.com.tw/client/img/btn1.png">
</a>
</body></html>
"""

_VALID_CREDS = {
    "national_id": "A123456789",
    "roc_birthday": "0750101",
}

_PATCH_SETTINGS = (
    "ccas.ingestor.fetcher.banks.fubon.get_settings"
)


def _make_settings(tmp_path: Path) -> Settings:
    staging = tmp_path / "staging"
    staging.mkdir()
    manual = tmp_path / "manual-staging" / "FUBON"
    manual.mkdir(parents=True)
    return Settings(
        _env_file=None,
        api_token="test",
        staging_dir=str(staging),
        fubon_manual_staging_dir=str(manual),
    )


def _write_pdf(
    path: Path, content: bytes = b"%PDF-1.4\nfake",
) -> None:
    path.write_bytes(content)


def _spa_error(msg: str = "spa_not_implemented") -> FetchError:
    return FetchError("FUBON", msg)


class TestManualStagingEmpty:
    """Scenario 1: empty dir → FetchError with guidance."""

    def test_empty_dir_raises_with_guidance(
        self, tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        fetcher = FubonFetcher()

        with (
            patch.object(
                flow, "download",
                AsyncMock(side_effect=_spa_error()),
            ),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            with pytest.raises(
                FetchError, match="manual-staging",
            ):
                fetcher.fetch_pdf(_SPA_HTML, _VALID_CREDS)


class TestManualStagingMonthMatch:
    """Scenario 2: filename contains billing month."""

    def test_exact_month_match_and_move(
        self, tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        manual_dir = Path(settings.fubon_manual_staging_dir)
        staging_dir = Path(settings.staging_dir)

        pdf = manual_dir / "fubon-2026-03.pdf"
        other = manual_dir / "fubon-2026-04.pdf"
        _write_pdf(pdf, b"%PDF-1.4\nMarch")
        _write_pdf(other, b"%PDF-1.4\nApril")

        fetcher = FubonFetcher()
        html = (
            "<html><body>"
            "<p>2026\u5E7403\u6708\u4FE1\u7528\u5361\u5E33\u55AE</p>"
            '<a href="https://fbmbill.taipeifubon.com.tw/abc">'
            "link</a></body></html>"
        )

        with (
            patch.object(
                flow, "download",
                AsyncMock(side_effect=_spa_error()),
            ),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            result = fetcher.fetch_pdf(html, _VALID_CREDS)

        assert result == b"%PDF-1.4\nMarch"
        assert not pdf.exists()
        dest = staging_dir / "FUBON" / "fubon-2026-03.pdf"
        assert dest.exists()
        assert other.exists()


class TestManualStagingSingleNoMonth:
    """Scenario 3: single file without month → pick it."""

    def test_single_file_picked(
        self, tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        manual_dir = Path(settings.fubon_manual_staging_dir)

        pdf = manual_dir / "statement.pdf"
        _write_pdf(pdf, b"%PDF-1.4\nsingle")

        fetcher = FubonFetcher()
        with (
            patch.object(
                flow, "download",
                AsyncMock(side_effect=_spa_error()),
            ),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            result = fetcher.fetch_pdf(
                _SPA_HTML, _VALID_CREDS,
            )

        assert result == b"%PDF-1.4\nsingle"
        assert not pdf.exists()


class TestManualStagingMultipleAmbiguous:
    """Scenario 4: multiple files without month → error."""

    def test_multiple_ambiguous_raises(
        self, tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        manual_dir = Path(settings.fubon_manual_staging_dir)

        _write_pdf(manual_dir / "a.pdf")
        _write_pdf(manual_dir / "b.pdf")

        fetcher = FubonFetcher()
        with (
            patch.object(
                flow, "download",
                AsyncMock(side_effect=_spa_error()),
            ),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            with pytest.raises(FetchError, match="無法對應"):
                fetcher.fetch_pdf(
                    _SPA_HTML, _VALID_CREDS,
                )


class TestManualStagingSpaFallback:
    """Scenario 5: SPA failure → fallback succeeds."""

    def test_spa_failure_falls_back(
        self, tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        manual_dir = Path(settings.fubon_manual_staging_dir)

        _write_pdf(
            manual_dir / "fubon-2026-03.pdf",
            b"%PDF-1.4\nfallback",
        )

        fetcher = FubonFetcher()
        html = (
            "<html><body><p>2026\u5E7403\u6708</p>"
            '<a href="https://fbmbill.taipeifubon.com.tw/x">'
            "link</a></body></html>"
        )

        err = _spa_error(
            "captcha_retry_exhausted: 7 attempts failed",
        )
        with (
            patch.object(
                flow, "download",
                AsyncMock(side_effect=err),
            ),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            result = fetcher.fetch_pdf(html, _VALID_CREDS)

        assert result == b"%PDF-1.4\nfallback"
