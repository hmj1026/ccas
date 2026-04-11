"""FubonFetcher unit tests (SPA migration edition).

FUBON 帳單下載系統已於某時點遷移為 Vue SPA + axios API 架構，
舊版 CAPTCHA flow 相關測試已移除。詳見
openspec/changes/fix-fubon-fetcher-spa-migration/。
"""

from __future__ import annotations

import pytest

from ccas.ingestor.fetcher.banks.fubon import (
    _ALLOWED_DOMAINS,
    FubonFetcher,
    _validate_url,
)
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


class TestExtractDownloadUrl:
    """FubonFetcher._extract_download_url() tests."""

    def test_extracts_legacy_anchor_href(self):
        fetcher = FubonFetcher()
        url = fetcher._extract_download_url(_LEGACY_TEXT_ANCHOR_HTML)
        assert url == "https://mybank.taipeifubon.com.tw/download?token=abc123"

    def test_extracts_spa_anchor_href(self):
        """SPA 時代錨點：優先回傳 fbmbill 網域連結。"""
        fetcher = FubonFetcher()
        url = fetcher._extract_download_url(_SPA_IMG_ANCHOR_HTML)
        assert url.startswith("https://fbmbill.taipeifubon.com.tw/")

    def test_missing_link_raises_fetch_error(self):
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="找不到帳單下載連結"):
            fetcher._extract_download_url(_NO_LINK_HTML)

    def test_non_fubon_domain_raises(self):
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="找不到帳單下載連結"):
            fetcher._extract_download_url(_NON_FUBON_DOMAIN_HTML)


class TestFetchPdf:
    """FubonFetcher.fetch_pdf() tests (SPA edition)."""

    def test_missing_credentials_raises(self):
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="缺少"):
            fetcher.fetch_pdf(
                _SPA_IMG_ANCHOR_HTML,
                {"national_id": "", "roc_birthday": ""},
            )

    def test_fetch_pdf_raises_spa_not_implemented(self):
        """SPA 網域下載請求應立即拋出明確錯誤，而非嘗試舊 CAPTCHA 流程。"""
        fetcher = FubonFetcher()
        with pytest.raises(FetchError) as exc_info:
            fetcher.fetch_pdf(
                _SPA_IMG_ANCHOR_HTML,
                {"national_id": "A123456789", "roc_birthday": "0750101"},
            )
        assert exc_info.value.bank_code == "FUBON"
        assert "SPA" in str(exc_info.value)
        assert "尚未實作" in str(exc_info.value)

    def test_fetch_pdf_legacy_url_also_not_implemented(self):
        """即使是舊格式 URL（mybank 網域），fetch 流程現階段全面未實作。"""
        fetcher = FubonFetcher()
        with pytest.raises(FetchError) as exc_info:
            fetcher.fetch_pdf(
                _LEGACY_TEXT_ANCHOR_HTML,
                {"national_id": "A123456789", "roc_birthday": "0750101"},
            )
        assert exc_info.value.bank_code == "FUBON"
        assert "尚未實作" in str(exc_info.value)


class TestRegistryRegistration:
    """Module-level registration test."""

    def test_fubon_registered(self):
        from ccas.ingestor.fetcher.registry import fetcher_registry

        fetcher = fetcher_registry.get("FUBON")
        assert fetcher is not None
        assert isinstance(fetcher, BankFetcher)
        assert fetcher.bank_code == "FUBON"


class TestUrlValidation:
    """_validate_url() domain allowlist tests."""

    def test_valid_https_legacy_domain_passes(self):
        _validate_url(
            "https://mybank.taipeifubon.com.tw/bill/download",
            context="test",
        )

    def test_fbmbill_domain_passes(self):
        """SPA 時代新網域必須在白名單內。"""
        _validate_url(
            "https://fbmbill.taipeifubon.com.tw/client/pdf/abc123",
            context="test",
        )

    def test_http_scheme_rejected(self):
        with pytest.raises(FetchError, match="HTTPS"):
            _validate_url(
                "http://mybank.taipeifubon.com.tw/bill",
                context="test",
            )

    def test_disallowed_domain_rejected(self):
        with pytest.raises(FetchError, match="允許清單"):
            _validate_url(
                "https://evil.example.com/phish",
                context="test",
            )

    def test_all_allowed_domains_pass(self):
        for domain in _ALLOWED_DOMAINS:
            _validate_url(f"https://{domain}/path", context="test")

    def test_userinfo_bypass_rejected(self):
        with pytest.raises(FetchError, match="userinfo"):
            _validate_url(
                "https://evil.com@mybank.taipeifubon.com.tw/path",
                context="test",
            )

    def test_subdomain_suffix_confusion_rejected(self):
        with pytest.raises(FetchError, match="允許清單"):
            _validate_url(
                "https://mybank.taipeifubon.com.tw.evil.com/path",
                context="test",
            )

    def test_protocol_relative_url_rejected(self):
        with pytest.raises(FetchError, match="HTTPS"):
            _validate_url("//mybank.taipeifubon.com.tw/path", context="test")
