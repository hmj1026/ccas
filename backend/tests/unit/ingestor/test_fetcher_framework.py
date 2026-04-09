"""Fetcher framework unit tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from ccas.ingestor.fetcher.base import BankFetcher, FetchError
from ccas.ingestor.fetcher.registry import _FetcherRegistry
from ccas.ingestor.gmail_client import GmailMessage

# -- Concrete stub for testing abstract BankFetcher --


class _StubFetcher(BankFetcher):
    """Minimal concrete BankFetcher for testing."""

    @property
    def bank_code(self) -> str:
        return "STUB"

    def can_fetch(self, html_body: str) -> bool:
        return "download" in html_body.lower()

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        return b"%PDF-stub"


class TestBankFetcherSubclassing:
    """BankFetcher ABC subclassing tests."""

    def test_concrete_fetcher_instantiation(self):
        """Concrete subclass can be instantiated."""
        fetcher = _StubFetcher()
        assert fetcher.bank_code == "STUB"

    def test_can_fetch_positive(self):
        """can_fetch returns True when HTML matches."""
        fetcher = _StubFetcher()
        assert fetcher.can_fetch("<a>Download</a>") is True

    def test_can_fetch_negative(self):
        """can_fetch returns False when HTML does not match."""
        fetcher = _StubFetcher()
        assert fetcher.can_fetch("<p>No link here</p>") is False

    def test_fetch_pdf_returns_bytes(self):
        """fetch_pdf returns PDF bytes."""
        fetcher = _StubFetcher()
        result = fetcher.fetch_pdf("<a>download</a>", {})
        assert result == b"%PDF-stub"

    def test_abstract_methods_enforced(self):
        """Cannot instantiate BankFetcher without implementing abstract methods."""
        with pytest.raises(TypeError):
            BankFetcher()  # type: ignore[abstract]


class TestFetcherRegistry:
    """_FetcherRegistry register/get/clear tests."""

    def test_register_and_get(self):
        """Registered fetcher can be retrieved by bank_code."""
        reg = _FetcherRegistry()
        fetcher = _StubFetcher()
        reg.register(fetcher)
        assert reg.get("STUB") is fetcher

    def test_get_case_insensitive(self):
        """get() is case-insensitive."""
        reg = _FetcherRegistry()
        reg.register(_StubFetcher())
        assert reg.get("stub") is not None
        assert reg.get("Stub") is not None

    def test_get_unknown_returns_none(self):
        """get() returns None for unregistered bank_code."""
        reg = _FetcherRegistry()
        assert reg.get("UNKNOWN") is None

    def test_clear(self):
        """clear() removes all registered fetchers."""
        reg = _FetcherRegistry()
        reg.register(_StubFetcher())
        reg.clear()
        assert reg.get("STUB") is None

    def test_register_overwrites(self):
        """Registering a second fetcher with same bank_code overwrites."""
        reg = _FetcherRegistry()

        class _AnotherStub(BankFetcher):
            @property
            def bank_code(self) -> str:
                return "STUB"

            def can_fetch(self, html_body: str) -> bool:
                return False

            def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
                return b""

        first = _StubFetcher()
        second = _AnotherStub()
        reg.register(first)
        reg.register(second)
        assert reg.get("STUB") is second


class TestFetchError:
    """FetchError exception tests."""

    def test_includes_bank_code_in_message(self):
        """Error message includes bank_code prefix."""
        err = FetchError("FUBON", "connection failed")
        assert "[FUBON]" in str(err)
        assert "connection failed" in str(err)

    def test_bank_code_attribute(self):
        """bank_code attribute is accessible."""
        err = FetchError("CTBC", "timeout")
        assert err.bank_code == "CTBC"

    def test_inherits_from_exception(self):
        """FetchError inherits from Exception."""
        err = FetchError("TEST", "msg")
        assert isinstance(err, Exception)


class TestGmailMessageHtmlBody:
    """GmailMessage dataclass with html_body field tests."""

    def test_default_html_body_is_none(self):
        """html_body defaults to None."""
        msg = GmailMessage(
            message_id="msg-001",
            message_date=datetime(2026, 3, 10),
            pdf_attachments=(),
        )
        assert msg.html_body is None

    def test_html_body_set_explicitly(self):
        """html_body can be set explicitly."""
        msg = GmailMessage(
            message_id="msg-002",
            message_date=datetime(2026, 3, 10),
            pdf_attachments=(),
            html_body="<html>test</html>",
        )
        assert msg.html_body == "<html>test</html>"

    def test_frozen_dataclass(self):
        """GmailMessage is frozen (immutable)."""
        msg = GmailMessage(
            message_id="msg-003",
            message_date=datetime(2026, 3, 10),
            pdf_attachments=(),
        )
        with pytest.raises(AttributeError):
            msg.html_body = "changed"  # type: ignore[misc]
