"""台北富邦銀行 (FUBON) web-fetch implementation.

``can_fetch`` detects any FUBON-owned bill link in the email HTML.
``fetch_pdf`` validates credentials and delegates to :mod:`.flow` which
drives the SPA API: open_spa → captcha(+retry+optional LLM) → doLogin →
main-info → PDFReportProc.

Credentials come from the standard ``credentials`` dict keys
(``national_id``, ``roc_birthday``) populated by ``job.py`` from
``FUBON_NATIONAL_ID`` / ``FUBON_ROC_BIRTHDAY`` env vars. Tuning knobs
(``fubon_captcha_max_retries``, ``fubon_captcha_fallback_llm``) live on
``Settings`` and are read at call time.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ccas.config import get_settings
from ccas.ingestor.fetcher.banks.fubon import flow
from ccas.ingestor.fetcher.base import BankFetcher, FetchError
from ccas.ingestor.fetcher.registry import fetcher_registry

_ID_RE = re.compile(r"^[A-Z][12]\d{8}$")
_BIRTHDAY_RE = re.compile(r"^\d{7}$")

logger = logging.getLogger(__name__)

# Strict HTTPS domain allowlist for FUBON-owned hosts. ``can_fetch`` uses
# this to decide whether the email references a FUBON bill link. Legacy
# hosts remain in the set so historical emails still route correctly;
# ``fbmbill.taipeifubon.com.tw`` is the SPA landing host used by the
# current download service.
_ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        "mybank.taipeifubon.com.tw",
        "ecard.taipeifubon.com.tw",
        "ebill.taipeifubon.com.tw",
        "www.taipeifubon.com.tw",
        "cf.taipeifubon.com.tw",
        "fbmbill.taipeifubon.com.tw",
    }
)


class FubonFetcher(BankFetcher):
    """台北富邦銀行 web-fetch.

    ``can_fetch`` recognises any ``<a>`` anchor pointing at a FUBON-owned
    download host. ``fetch_pdf`` validates credentials and delegates to
    :func:`flow.download`, which runs the full SPA pipeline and returns
    PDF bytes.
    """

    @property
    def bank_code(self) -> str:
        return "FUBON"

    def can_fetch(self, html_body: str) -> bool:
        """Return True if the email HTML contains a link to a FUBON-owned host."""
        if not html_body or not html_body.strip():
            return False
        try:
            soup = BeautifulSoup(html_body, "html.parser")
        except (AttributeError, TypeError):
            logger.warning("FUBON can_fetch HTML 解析失敗", exc_info=True)
            return False
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            try:
                parsed = urlparse(href)
            except ValueError:
                continue
            # Require HTTPS + allowlisted host. Non-HTTPS FUBON links are
            # rejected so can_fetch cannot return True for an attacker-
            # controlled http:// URL pointing at a look-alike serial-key.
            if parsed.scheme != "https":
                continue
            if parsed.hostname in _ALLOWED_DOMAINS:
                return True
        return False

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        """Download the current FUBON bill PDF via the SPA JSON API.

        Delegates to :func:`flow.download` which runs the full async pipeline
        in a fresh event loop (this method is invoked via
        ``asyncio.to_thread`` from :mod:`ccas.ingestor.job`, so no outer loop
        exists in this thread).

        Args:
            html_body: Email HTML containing the bill download link.
            credentials: Must include ``national_id`` (10-char ROC id,
                ``^[A-Z][12]\\d{8}$``) and ``roc_birthday`` (7 digits).
                Format is validated here so a clear ``credentials_wrong``
                error surfaces early.

        Raises:
            FetchError: credentials missing / malformed, download link not
                found, or the underlying flow failed (captcha retries
                exhausted, doLogin rejected, HTTP error).
        """
        national_id = credentials.get("national_id", "").strip()
        roc_birthday = credentials.get("roc_birthday", "").strip()
        if not national_id or not roc_birthday:
            raise FetchError(
                self.bank_code,
                "credentials_missing: FUBON_NATIONAL_ID or FUBON_ROC_BIRTHDAY not set",
            )
        if not _ID_RE.match(national_id):
            raise FetchError(
                self.bank_code,
                "credentials_wrong: FUBON_NATIONAL_ID must match ^[A-Z][12]\\d{8}$",
            )
        if not _BIRTHDAY_RE.match(roc_birthday):
            raise FetchError(
                self.bank_code,
                "credentials_wrong: FUBON_ROC_BIRTHDAY must be 7 digits (ROC YYYMMDD)",
            )

        settings = get_settings()
        api_key = settings.anthropic_api_key.get_secret_value()
        return asyncio.run(
            flow.download(
                email_html=html_body,
                id_number=national_id,
                birthday=roc_birthday,
                max_retries=settings.fubon_captcha_max_retries,
                llm_fallback=settings.fubon_captcha_fallback_llm,
                llm_api_key=api_key or None,
            )
        )


fetcher_registry.register(FubonFetcher())
