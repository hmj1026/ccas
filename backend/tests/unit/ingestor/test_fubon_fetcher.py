"""FubonFetcher unit tests (SPA migration edition).

FUBON 帳單下載系統已於某時點遷移為 Vue SPA + axios API 架構，
舊版 CAPTCHA flow 相關測試已移除。詳見
openspec/changes/fix-fubon-fetcher-spa-migration/。
"""

from __future__ import annotations

import pytest

from ccas.ingestor.fetcher.banks.fubon import FubonFetcher
from ccas.ingestor.fetcher.base import BankFetcher, FetchError

# -- Test HTML fixtures --

_LEGACY_TEXT_ANCHOR_HTML = """
<html><body>
<a href="https://mybank.taipeifubon.com.tw/download?token=abc123">下載帳單明細</a>
</body></html>
"""

_SPA_IMG_ANCHOR_HTML = """
<html><body>
<a href="https://fbmbill.taipeifubon.com.tw/1e79254d8b8c42f1a5c15aa54a0c6616">
  <img border="0"
       src="https://fbmbill.taipeifubon.com.tw/client/img/btn1.png"
       alt="查看信用卡帳單" width="120">
</a>
<a href="https://fbmbill.taipeifubon.com.tw/client/pdf/1e79254d8b8c42f1a5c15aa54a0c6616">
  <img border="0"
       src="https://fbmbill.taipeifubon.com.tw/client/img/btn2.png"
       alt="下載本期帳單(PDF)" width="120">
</a>
</body></html>
"""

_NO_LINK_HTML = """
<html><body><p>No download link here</p></body></html>
"""

_NON_FUBON_DOMAIN_HTML = """
<html><body>
<a href="https://evil.example.com/steal">下載帳單明細</a>
<a href="https://www.google.com">搜尋</a>
</body></html>
"""


class TestCanFetch:
    """FubonFetcher.can_fetch() tests."""

    def test_can_fetch_recognizes_img_wrapped_anchor(self):
        """SPA 時代：錨點內為 <img>，仍應辨識為 FUBON 下載連結。"""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch(_SPA_IMG_ANCHOR_HTML) is True

    def test_can_fetch_recognizes_legacy_text_anchor(self):
        """相容舊格式：純文字錨點仍應辨識為 FUBON 下載連結。"""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch(_LEGACY_TEXT_ANCHOR_HTML) is True

    def test_can_fetch_rejects_non_fubon_domain(self):
        """錨點 href 指向非 FUBON 白名單網域時回傳 False。"""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch(_NON_FUBON_DOMAIN_HTML) is False

    def test_can_fetch_rejects_no_link_html(self):
        fetcher = FubonFetcher()
        assert fetcher.can_fetch(_NO_LINK_HTML) is False

    def test_can_fetch_empty_body(self):
        fetcher = FubonFetcher()
        assert fetcher.can_fetch("") is False

    def test_can_fetch_whitespace_body(self):
        fetcher = FubonFetcher()
        assert fetcher.can_fetch("   ") is False


class TestFetchPdf:
    """FubonFetcher.fetch_pdf() delegates to flow.download()."""

    def test_missing_credentials_raises(self):
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="credentials_missing"):
            fetcher.fetch_pdf(
                _SPA_IMG_ANCHOR_HTML,
                {"national_id": "", "roc_birthday": ""},
            )

    def test_invalid_id_format_raises_credentials_wrong(self):
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="credentials_wrong"):
            fetcher.fetch_pdf(
                _SPA_IMG_ANCHOR_HTML,
                {"national_id": "abc12345", "roc_birthday": "0750101"},
            )

    def test_invalid_birthday_format_raises_credentials_wrong(self):
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="credentials_wrong"):
            fetcher.fetch_pdf(
                _SPA_IMG_ANCHOR_HTML,
                {"national_id": "A123456789", "roc_birthday": "1985-01-01"},
            )

    def test_fetch_pdf_delegates_to_flow_and_returns_pdf(self):
        from unittest.mock import AsyncMock, patch

        from ccas.ingestor.fetcher.banks.fubon import flow

        fetcher = FubonFetcher()
        with patch.object(
            flow, "download", AsyncMock(return_value=b"%PDF-1.4\nfake")
        ) as mock_flow:
            result = fetcher.fetch_pdf(
                _SPA_IMG_ANCHOR_HTML,
                {"national_id": "A123456789", "roc_birthday": "0750101"},
            )
        assert result == b"%PDF-1.4\nfake"
        mock_flow.assert_awaited_once()
        assert mock_flow.await_args is not None
        kwargs = mock_flow.await_args.kwargs
        assert kwargs["id_number"] == "A123456789"
        assert kwargs["birthday"] == "0750101"
        assert kwargs["email_html"] == _SPA_IMG_ANCHOR_HTML
        assert kwargs["max_retries"] >= 1

    def test_fetch_pdf_wraps_flow_fetch_error(self):
        from unittest.mock import AsyncMock, patch

        from ccas.ingestor.fetcher.banks.fubon import flow

        fetcher = FubonFetcher()
        with patch.object(
            flow,
            "download",
            AsyncMock(
                side_effect=FetchError("FUBON", "captcha_retry_exhausted: 7")
            ),
        ):
            with pytest.raises(FetchError, match="captcha_retry_exhausted"):
                fetcher.fetch_pdf(
                    _SPA_IMG_ANCHOR_HTML,
                    {"national_id": "A123456789", "roc_birthday": "0750101"},
                )


class TestRegistryRegistration:
    """Module-level registration test."""

    def test_fubon_registered(self):
        from ccas.ingestor.fetcher.registry import fetcher_registry

        fetcher = fetcher_registry.get("FUBON")
        assert fetcher is not None
        assert isinstance(fetcher, BankFetcher)
        assert fetcher.bank_code == "FUBON"
