"""台北富邦銀行 (FUBON) web-fetch 實作。

現況（2026-04 實測）：
    富邦帳單下載系統已遷移為 Vue SPA + axios API 架構，不再使用
    server-rendered 表單 + CAPTCHA 圖片。本模組目前只實作「辨識含
    FUBON 官方網域下載連結的郵件」以便 pipeline 正確路由，實際下載
    流程（``fetch_pdf``）會直接拋出 ``FetchError`` 要求使用者手動
    處理。完整 SPA API + OTP 流程需另開變更反向工程後實作。

參考變更：``openspec/changes/archive/...-fix-fubon-fetcher-spa-migration``
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ccas.ingestor.fetcher.base import BankFetcher, FetchError
from ccas.ingestor.fetcher.registry import fetcher_registry

logger = logging.getLogger(__name__)

# Strict HTTPS domain allowlist for FUBON-owned hosts.
# All URLs extracted from email HTML are validated against this set
# before any request is made, to prevent credential exfiltration.
#
# ``fbmbill.taipeifubon.com.tw`` is the SPA landing host used by the
# current (post-migration) bill download service. Legacy hosts remain
# in the set so historical emails referencing mybank/ecard/ebill still
# route through ``can_fetch`` correctly.
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


def _validate_url(url: str, *, context: str = "") -> None:
    """Validate that *url* uses HTTPS and points to an allowed FUBON domain.

    Raises:
        FetchError: If the scheme is not HTTPS or the hostname is not in
            ``_ALLOWED_DOMAINS``.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise FetchError(
            "FUBON",
            f"URL scheme 不安全 ({context}): scheme={parsed.scheme}，僅允許 HTTPS",
        )
    if parsed.username or parsed.password:
        raise FetchError(
            "FUBON",
            f"URL 包含非法 userinfo ({context})",
        )
    if parsed.hostname not in _ALLOWED_DOMAINS:
        raise FetchError(
            "FUBON",
            f"URL 網域不在允許清單 ({context}): {parsed.hostname}",
        )


class FubonFetcher(BankFetcher):
    """台北富邦銀行 web-fetch。

    目前行為（SPA 遷移後）：
        * ``can_fetch`` 會辨識任何指向 FUBON 官方下載網域的 ``<a>`` 錨點
        * ``fetch_pdf`` 會立即拋出 ``FetchError`` 說明 SPA 流程尚未實作
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
                hostname = urlparse(href).hostname
            except ValueError:
                continue
            if hostname in _ALLOWED_DOMAINS:
                return True
        return False

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        """Attempt to download a FUBON bill PDF.

        The current (SPA-era) download system requires reverse-engineering
        a Vue SPA + axios ``doLogin`` flow with possible OTP verification,
        which is not yet implemented. This method validates credentials and
        the download URL domain, then raises ``FetchError`` with an explicit
        message so the pipeline JSON summary surfaces the unsupported state.

        Args:
            html_body: Email HTML containing the bill download link.
            credentials: Must include ``national_id`` and ``roc_birthday``
                (validated for future use even though not sent).

        Raises:
            FetchError: Always raised — missing credentials, missing link,
                or SPA flow not implemented.
        """
        national_id = credentials.get("national_id", "")
        roc_birthday = credentials.get("roc_birthday", "")
        if not national_id or not roc_birthday:
            raise FetchError(self.bank_code, "缺少 national_id 或 roc_birthday 憑證")

        url = self._extract_download_url(html_body)
        logger.info(
            "FUBON SPA download requested but not implemented",
            extra={"url_host": urlparse(url).hostname},
        )
        raise FetchError(
            self.bank_code,
            "富邦帳單系統已遷移為 SPA + API 流程（含可能的 OTP 驗證），"
            "自動下載尚未實作；請手動從網銀下載 PDF 後放入 staging 目錄。",
        )

    def _extract_download_url(self, html_body: str) -> str:
        """Extract the first FUBON-owned bill download URL from email HTML.

        Raises:
            FetchError: No FUBON-owned anchor was found in *html_body*.
        """
        soup = BeautifulSoup(html_body, "html.parser")
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            try:
                hostname = urlparse(href).hostname
            except ValueError:
                continue
            if hostname in _ALLOWED_DOMAINS:
                _validate_url(href, context="download URL")
                return href
        raise FetchError(self.bank_code, "找不到帳單下載連結")


# Module-level registration
fetcher_registry.register(FubonFetcher())
