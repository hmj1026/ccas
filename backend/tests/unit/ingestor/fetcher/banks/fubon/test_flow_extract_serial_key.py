"""Unit tests for flow._extract_serial_key — serial key extraction from email HTML."""

from __future__ import annotations

import pytest

from ccas.ingestor.fetcher.banks.fubon.flow import _extract_serial_key
from ccas.ingestor.fetcher.base import FetchError


class TestExtractSerialKey:
    def test_direct_link(self):
        html = (
            '<html><a href="https://fbmbill.taipeifubon.com.tw/abcdef123">x</a></html>'
        )
        assert _extract_serial_key(html) == "abcdef123"

    def test_client_pdf_prefix_stripped(self):
        html = (
            '<html><a href="https://fbmbill.taipeifubon.com.tw'
            '/client/pdf/1e79254d8b8c42f1">x</a></html>'
        )
        assert _extract_serial_key(html) == "1e79254d8b8c42f1"

    def test_picks_first_matching_link(self):
        html = (
            "<html>"
            '<a href="https://fbmbill.taipeifubon.com.tw/first_serial">a</a>'
            '<a href="https://fbmbill.taipeifubon.com.tw/second_serial">b</a>'
            "</html>"
        )
        assert _extract_serial_key(html) == "first_serial"

    def test_ignores_non_spa_host_links(self):
        html = (
            "<html>"
            '<a href="https://www.google.com/search">g</a>'
            '<a href="https://evil.com/serial123">e</a>'
            "</html>"
        )
        with pytest.raises(FetchError, match="no_download_link"):
            _extract_serial_key(html)

    def test_no_links_at_all(self):
        html = "<html><p>No links here</p></html>"
        with pytest.raises(FetchError, match="no_download_link"):
            _extract_serial_key(html)

    def test_empty_html(self):
        with pytest.raises(FetchError, match="no_download_link"):
            _extract_serial_key("")

    def test_malformed_href_skipped(self):
        html = (
            "<html>"
            '<a href="://broken[url">bad</a>'
            '<a href="https://fbmbill.taipeifubon.com.tw/good_serial">ok</a>'
            "</html>"
        )
        assert _extract_serial_key(html) == "good_serial"

    def test_strips_trailing_path_segments(self):
        html = (
            '<html><a href="https://fbmbill.taipeifubon.com.tw'
            '/abc123/extra/stuff">x</a></html>'
        )
        assert _extract_serial_key(html) == "abc123"

    def test_non_spa_host_in_allowed_domains_ignored(self):
        """Links to other FUBON domains (not SPA host) are not matched."""
        html = '<html><a href="https://mybank.taipeifubon.com.tw/download">x</a></html>'
        with pytest.raises(FetchError, match="no_download_link"):
            _extract_serial_key(html)

    def test_root_path_only_skipped(self):
        """An href with just the host and no path should not return empty string."""
        html = '<html><a href="https://fbmbill.taipeifubon.com.tw/">x</a></html>'
        with pytest.raises(FetchError, match="no_download_link"):
            _extract_serial_key(html)

    def test_http_scheme_not_matched(self):
        """_extract_serial_key uses hostname check, not scheme — verify behaviour."""
        html = '<html><a href="http://fbmbill.taipeifubon.com.tw/serial">x</a></html>'
        assert _extract_serial_key(html) == "serial"
