"""FubonFetcher unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import (
    _ALLOWED_DOMAINS,
    FubonFetcher,
    _validate_url,
)
from ccas.ingestor.fetcher.base import BankFetcher, FetchError

# -- Test HTML fixtures --

_VALID_HTML = """
<html><body>
<a href="https://mybank.taipeifubon.com.tw/download?token=abc123">下載帳單明細</a>
</body></html>
"""

_NO_LINK_HTML = """
<html><body><p>No download link here</p></body></html>
"""

_DOWNLOAD_PAGE_HTML = """
<html><body>
<form action="/submit">
  <input type="hidden" name="csrf_token" value="xyz" />
  <input type="text" name="nationalId" />
  <input type="text" name="birthday" />
  <input type="text" name="captcha_code" />
  <img id="captchaImg" src="/captcha.png" />
</form>
</body></html>
"""


class TestCanFetch:
    """FubonFetcher.can_fetch() tests."""

    def test_positive(self):
        """Returns True when HTML contains the download link text."""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch(_VALID_HTML) is True

    def test_negative(self):
        """Returns False when HTML has no download link."""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch(_NO_LINK_HTML) is False

    def test_empty_body(self):
        """Returns False for empty string."""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch("") is False

    def test_none_like_empty(self):
        """Returns False for whitespace-only body."""
        fetcher = FubonFetcher()
        assert fetcher.can_fetch("   ") is False


class TestExtractDownloadUrl:
    """FubonFetcher._extract_download_url() tests."""

    def test_extracts_href(self):
        """Extracts the correct URL from the download link."""
        fetcher = FubonFetcher()
        url = fetcher._extract_download_url(_VALID_HTML)
        assert url == "https://mybank.taipeifubon.com.tw/download?token=abc123"

    def test_missing_link_raises_fetch_error(self):
        """Raises FetchError when no download link is found."""
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="找不到帳單下載連結"):
            fetcher._extract_download_url(_NO_LINK_HTML)


def _make_page_response(url: str = "https://mybank.taipeifubon.com.tw/download"):
    """Create a mock httpx.Response for the download page."""
    resp = MagicMock()
    resp.text = _DOWNLOAD_PAGE_HTML
    resp.url = url
    return resp


def _make_captcha_response():
    """Create a mock httpx.Response for the CAPTCHA image."""
    resp = MagicMock()
    resp.content = b"\x89PNG-captcha"
    return resp


def _make_pdf_response():
    """Create a mock httpx.Response for the PDF download."""
    resp = MagicMock()
    resp.headers = {"content-type": "application/pdf"}
    resp.content = b"%PDF-1.4 fake"
    resp.url = "https://mybank.taipeifubon.com.tw/download/bill.pdf"
    return resp


def _make_non_pdf_response():
    """Create a mock httpx.Response that is NOT a PDF (CAPTCHA failure page)."""
    resp = MagicMock()
    resp.headers = {"content-type": "text/html"}
    resp.content = b"<html>Error</html>"
    resp.url = "https://mybank.taipeifubon.com.tw/error"
    return resp


class TestFetchPdf:
    """FubonFetcher.fetch_pdf() tests."""

    def test_missing_credentials_raises(self):
        """Raises FetchError when national_id or roc_birthday is missing."""
        fetcher = FubonFetcher()
        with pytest.raises(FetchError, match="缺少"):
            fetcher.fetch_pdf(_VALID_HTML, {"national_id": "", "roc_birthday": ""})

    @patch("ccas.ingestor.fetcher.banks.fubon.solve_captcha")
    def test_success(self, mock_solve):
        """Successfully downloads PDF with valid CAPTCHA."""
        mock_solve.return_value = "ABCD"

        mock_client = MagicMock()
        page_resp = _make_page_response()
        captcha_resp = _make_captcha_response()
        pdf_resp = _make_pdf_response()

        mock_client.get.side_effect = [page_resp, captcha_resp]
        mock_client.post.return_value = pdf_resp

        with patch("httpx.Client") as mock_httpx_client:
            mock_httpx_client.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)

            fetcher = FubonFetcher()
            result = fetcher.fetch_pdf(
                _VALID_HTML,
                {"national_id": "A123456789", "roc_birthday": "0750101"},
            )

        assert result == b"%PDF-1.4 fake"
        mock_solve.assert_called_once_with(b"\x89PNG-captcha")

    @patch("ccas.ingestor.fetcher.banks.fubon.solve_captcha")
    def test_captcha_retry_success(self, mock_solve):
        """First 2 CAPTCHAs fail (empty string), third succeeds."""
        mock_solve.side_effect = ["", "", "GOOD"]

        mock_client = MagicMock()
        page_resp = _make_page_response()
        captcha_resp = _make_captcha_response()
        pdf_resp = _make_pdf_response()

        # Attempt 1: page + captcha (fail) -> retry page
        # Attempt 2: page + captcha (fail) -> retry page
        # Attempt 3: page + captcha (success) -> post -> pdf
        mock_client.get.side_effect = [
            page_resp,  # initial page load
            captcha_resp,  # attempt 1 captcha
            page_resp,  # retry page load
            captcha_resp,  # attempt 2 captcha
            page_resp,  # retry page load
            captcha_resp,  # attempt 3 captcha
        ]
        mock_client.post.return_value = pdf_resp

        with patch("httpx.Client") as mock_httpx_client:
            mock_httpx_client.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)

            fetcher = FubonFetcher()
            result = fetcher.fetch_pdf(
                _VALID_HTML,
                {"national_id": "A123456789", "roc_birthday": "0750101"},
            )

        assert result == b"%PDF-1.4 fake"
        assert mock_solve.call_count == 3

    @patch("ccas.ingestor.fetcher.banks.fubon.solve_captcha")
    def test_all_captcha_fail(self, mock_solve):
        """All 3 CAPTCHA attempts fail -> raises FetchError."""
        mock_solve.return_value = ""

        mock_client = MagicMock()
        page_resp = _make_page_response()
        captcha_resp = _make_captcha_response()

        mock_client.get.side_effect = [
            page_resp,
            captcha_resp,
            page_resp,
            captcha_resp,
            page_resp,
            captcha_resp,
        ]

        with patch("httpx.Client") as mock_httpx_client:
            mock_httpx_client.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)

            fetcher = FubonFetcher()
            with pytest.raises(FetchError, match="CAPTCHA 辨識失敗"):
                fetcher.fetch_pdf(
                    _VALID_HTML,
                    {"national_id": "A123456789", "roc_birthday": "0750101"},
                )

    @patch("ccas.ingestor.fetcher.banks.fubon.solve_captcha")
    def test_non_pdf_response_triggers_retry(self, mock_solve):
        """Non-PDF response after form submit triggers CAPTCHA retry."""
        mock_solve.side_effect = ["ABCD", "EFGH"]

        mock_client = MagicMock()
        page_resp = _make_page_response()
        captcha_resp = _make_captcha_response()
        non_pdf_resp = _make_non_pdf_response()
        pdf_resp = _make_pdf_response()

        mock_client.get.side_effect = [
            page_resp,
            captcha_resp,  # attempt 1
            page_resp,
            captcha_resp,  # attempt 2
        ]
        mock_client.post.side_effect = [non_pdf_resp, pdf_resp]

        with patch("httpx.Client") as mock_httpx_client:
            mock_httpx_client.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)

            fetcher = FubonFetcher()
            result = fetcher.fetch_pdf(
                _VALID_HTML,
                {"national_id": "A123456789", "roc_birthday": "0750101"},
            )

        assert result == b"%PDF-1.4 fake"


class TestRegistryRegistration:
    """Module-level registration test."""

    def test_fubon_registered(self):
        """Importing the module triggers fetcher_registry registration."""
        from ccas.ingestor.fetcher.registry import fetcher_registry

        fetcher = fetcher_registry.get("FUBON")
        assert fetcher is not None
        assert isinstance(fetcher, BankFetcher)
        assert fetcher.bank_code == "FUBON"


class TestUrlValidation:
    """_validate_url() domain allowlist tests."""

    def test_valid_https_allowed_domain_passes(self):
        _validate_url(
            "https://mybank.taipeifubon.com.tw/bill/download",
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

    def test_extract_url_rejects_disallowed_domain(self):
        """_extract_download_url rejects links pointing to non-FUBON domains."""
        fetcher = FubonFetcher()
        evil_html = (
            "<html><body>"
            '<a href="https://evil.example.com/steal">下載帳單明細</a>'
            "</body></html>"
        )
        with pytest.raises(FetchError, match="允許清單"):
            fetcher._extract_download_url(evil_html)

    def test_userinfo_bypass_rejected(self):
        """URL with userinfo (user@host) must be rejected."""
        with pytest.raises(FetchError, match="userinfo"):
            _validate_url(
                "https://evil.com@mybank.taipeifubon.com.tw/path",
                context="test",
            )

    def test_subdomain_suffix_confusion_rejected(self):
        """Domain ending with allowed suffix but different TLD is rejected."""
        with pytest.raises(FetchError, match="允許清單"):
            _validate_url(
                "https://mybank.taipeifubon.com.tw.evil.com/path",
                context="test",
            )

    def test_protocol_relative_url_rejected(self):
        """Protocol-relative URL (//host/path) has empty scheme and is rejected."""
        with pytest.raises(FetchError, match="HTTPS"):
            _validate_url("//mybank.taipeifubon.com.tw/path", context="test")
