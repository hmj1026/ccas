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
import shutil
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ccas.config import get_settings
from ccas.ingestor.fetcher.banks.fubon import flow
from ccas.ingestor.fetcher.base import BankFetcher, FetchError
from ccas.ingestor.fetcher.registry import fetcher_registry

_ID_RE = re.compile(r"^[A-Z][12]\d{8}$")
_BIRTHDAY_RE = re.compile(r"^\d{7}$")
_BILLING_MONTH_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
# Credential error prefixes — FetchError messages starting with these
# must NOT fall through to manual-staging (surface to operator instead).
_CREDENTIAL_ERROR_PREFIXES = (
    "credentials_missing:",
    "credentials_wrong:",
)

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


def _extract_billing_month(html_body: str) -> str | None:
    """Try to extract ``YYYY-MM`` billing month from email HTML."""
    match = _BILLING_MONTH_RE.search(html_body)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return None


class FubonFetcher(BankFetcher):
    """台北富邦銀行 web-fetch.

    ``can_fetch`` recognises any ``<a>`` anchor pointing at a FUBON-owned
    download host. ``fetch_pdf`` validates credentials and delegates to
    :func:`flow.download`, which runs the full SPA pipeline and returns
    PDF bytes. When the SPA path fails, falls back to a manual-staging
    directory where the user can place a pre-downloaded PDF.
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
            if parsed.scheme != "https":
                continue
            if parsed.hostname in _ALLOWED_DOMAINS:
                return True
        return False

    def _try_manual_staging(self, billing_month: str | None) -> Path:
        """Find a PDF in the manual-staging directory and move it to staging.

        Args:
            billing_month: ``YYYY-MM`` string or None.

        Returns:
            Destination path after move.

        Raises:
            FetchError: No suitable file found.
        """
        settings = get_settings()
        manual_dir = Path(settings.fubon_manual_staging_dir)
        staging_dest = Path(settings.staging_dir) / "FUBON"

        if not manual_dir.exists():
            raise FetchError(
                self.bank_code,
                "manual_staging_not_found: "
                f"目錄 {manual_dir} 不存在。"
                "請建立目錄或確認 FUBON_MANUAL_STAGING_DIR 設定。",
            )

        pdfs = sorted(manual_dir.glob("*.pdf"))
        if not pdfs:
            raise FetchError(
                self.bank_code,
                f"manual_staging_empty: manual-staging 目錄 {manual_dir} 無 PDF 檔案。"
                "請從富邦網銀下載 PDF 並放入該目錄後重試。"
                "Docker 環境下 host 路徑為 ./backend/data/manual-staging/FUBON/",
            )

        chosen: Path | None = None
        if billing_month:
            compact = billing_month.replace("-", "")
            for pdf in pdfs:
                if billing_month in pdf.name or compact in pdf.name:
                    chosen = pdf
                    break

        if chosen is None:
            if len(pdfs) == 1:
                chosen = pdfs[0]
            else:
                raise FetchError(
                    self.bank_code,
                    f"manual_staging_ambiguous: manual-staging 目錄有 {len(pdfs)} 個"
                    "無法對應的檔案。請保留單一 PDF 或以 fubon-YYYY-MM.pdf 命名。"
                    f"目錄：{manual_dir}",
                )

        staging_dest.mkdir(parents=True, exist_ok=True)
        dest = staging_dest / chosen.name
        if dest.exists():
            raise FetchError(
                self.bank_code,
                f"manual_staging_conflict: {dest} 已存在。請移除後重試。",
            )
        shutil.move(chosen, dest)
        logger.info(
            "manual-staging fallback: %s → %s",
            chosen.name,
            dest,
        )
        return dest

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        """Download the current FUBON bill PDF via the SPA JSON API.

        Falls back to manual-staging directory when the SPA path fails
        (but not for credential errors).

        Args:
            html_body: Email HTML containing the bill download link.
            credentials: Must include ``national_id`` and ``roc_birthday``.

        Raises:
            FetchError: credentials missing / malformed, or both SPA and
                manual-staging paths failed.
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

        try:
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
        except FetchError as exc:
            msg = str(exc)
            if any(p in msg for p in _CREDENTIAL_ERROR_PREFIXES):
                raise
            logger.info("SPA fetch 失敗，嘗試 manual-staging fallback: %s", exc)
            billing_month = _extract_billing_month(html_body)
            path = self._try_manual_staging(billing_month)
            return path.read_bytes()


fetcher_registry.register(FubonFetcher())
