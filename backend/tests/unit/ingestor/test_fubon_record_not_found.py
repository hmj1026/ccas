"""FubonFetcher record_not_found soft-skip tests.

`record_not_found` 代表 FUBON email 下載連結的 serial_key 已失效（一次性使用
過期或已被下載），屬於永久性軟跳過，**不應** 落入 manual-staging fallback。

這類錯誤必須被 fetcher 直接 re-raise，讓上層 ingest job 將
`staged_attachments.status` 標記為 `fetch_expired`，並從此不再自動重試。
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

_PATCH_SETTINGS = "ccas.ingestor.fetcher.banks.fubon.get_settings"


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


class TestRecordNotFoundRaisesWithoutFallback:
    """record_not_found 必須直接 raise，不落入 manual-staging。"""

    def test_record_not_found_bypasses_manual_staging(
        self,
        tmp_path: Path,
    ) -> None:
        """即使 manual-staging 有檔案，record_not_found 也應直接 raise。"""
        settings = _make_settings(tmp_path)
        manual_dir = Path(settings.fubon_manual_staging_dir)
        # 故意放一個 PDF，驗證 record_not_found 不會誤用 fallback
        (manual_dir / "fubon-2026-03.pdf").write_bytes(b"%PDF-1.4\nX")

        err = FetchError(
            "FUBON",
            "record_not_found: doLogin msg='查無資料'",
        )
        fetcher = FubonFetcher()

        with (
            patch.object(flow, "download", AsyncMock(side_effect=err)),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            with pytest.raises(FetchError, match="record_not_found"):
                fetcher.fetch_pdf(_SPA_HTML, _VALID_CREDS)

    def test_credentials_missing_still_raises_without_fallback(
        self,
        tmp_path: Path,
    ) -> None:
        """回歸測試：credentials_missing 既有行為保留。"""
        settings = _make_settings(tmp_path)
        fetcher = FubonFetcher()

        err = FetchError(
            "FUBON",
            "credentials_missing: FUBON_NATIONAL_ID not set",
        )
        with (
            patch.object(flow, "download", AsyncMock(side_effect=err)),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            with pytest.raises(FetchError, match="credentials_missing"):
                fetcher.fetch_pdf(_SPA_HTML, _VALID_CREDS)

    def test_other_fetch_error_still_falls_back(
        self,
        tmp_path: Path,
    ) -> None:
        """回歸測試：其他錯誤仍應落入 manual-staging fallback。"""
        settings = _make_settings(tmp_path)
        manual_dir = Path(settings.fubon_manual_staging_dir)
        (manual_dir / "fubon-2026-03.pdf").write_bytes(b"%PDF-1.4\nfallback")

        err = FetchError(
            "FUBON",
            "captcha_retry_exhausted: 7 attempts failed",
        )
        fetcher = FubonFetcher()
        html = (
            "<html><body><p>2026\u5e7403\u6708</p>"
            '<a href="https://fbmbill.taipeifubon.com.tw/x">link</a>'
            "</body></html>"
        )

        with (
            patch.object(flow, "download", AsyncMock(side_effect=err)),
            patch(_PATCH_SETTINGS, return_value=settings),
        ):
            result = fetcher.fetch_pdf(html, _VALID_CREDS)

        assert result == b"%PDF-1.4\nfallback"
