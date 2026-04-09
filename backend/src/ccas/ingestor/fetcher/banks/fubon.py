"""台北富邦銀行 (FUBON) web-fetch 實作。

FUBON 帳單郵件不含 PDF 附件，而是包含一個下載連結。
使用者需填寫身分證字號、生日及 CAPTCHA 驗證碼後方可下載 PDF。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ccas.ingestor.fetcher.base import BankFetcher, FetchError
from ccas.ingestor.fetcher.captcha import solve_captcha
from ccas.ingestor.fetcher.registry import fetcher_registry

logger = logging.getLogger(__name__)

_MAX_CAPTCHA_RETRIES = 3
_DOWNLOAD_LINK_TEXT = "下載帳單明細"

# Strict HTTPS domain allowlist for FUBON-owned hosts.
# All URLs extracted from email HTML are validated against this set
# before any request is made, to prevent credential exfiltration.
_ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        "mybank.taipeifubon.com.tw",
        "ecard.taipeifubon.com.tw",
        "ebill.taipeifubon.com.tw",
        "www.taipeifubon.com.tw",
        "cf.taipeifubon.com.tw",
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


class _CaptchaFailedError(Exception):
    """Internal signal for CAPTCHA retry logic."""


class FubonFetcher(BankFetcher):
    """台北富邦銀行 web-fetch：從郵件 HTML 中取得帳單下載連結，填表下載 PDF。"""

    @property
    def bank_code(self) -> str:
        return "FUBON"

    def can_fetch(self, html_body: str) -> bool:
        """Check whether the email HTML contains a FUBON bill download link."""
        if not html_body:
            return False
        try:
            soup = BeautifulSoup(html_body, "html.parser")
            pattern = re.compile(_DOWNLOAD_LINK_TEXT)
            link = soup.find("a", string=pattern)  # type: ignore[call-overload]
            return link is not None
        except Exception:
            logger.debug("FUBON can_fetch HTML 解析失敗", exc_info=True)
            return False

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        """Download the PDF bill via FUBON's web form with CAPTCHA.

        Args:
            html_body: Email HTML containing the download link.
            credentials: Must include ``national_id`` and ``roc_birthday``.

        Returns:
            Downloaded PDF bytes.

        Raises:
            FetchError: Missing credentials, CAPTCHA failure, or download error.
        """
        import httpx

        url = self._extract_download_url(html_body)
        national_id = credentials.get("national_id", "")
        roc_birthday = credentials.get("roc_birthday", "")

        if not national_id or not roc_birthday:
            raise FetchError(self.bank_code, "缺少 national_id 或 roc_birthday 憑證")

        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            page_resp = client.get(url)
            page_resp.raise_for_status()
            _validate_url(str(page_resp.url), context="redirect target")

            for attempt in range(1, _MAX_CAPTCHA_RETRIES + 1):
                try:
                    return self._attempt_download(
                        client, page_resp, national_id, roc_birthday, attempt
                    )
                except _CaptchaFailedError:
                    if attempt < _MAX_CAPTCHA_RETRIES:
                        logger.warning(
                            "CAPTCHA 辨識失敗 (嘗試 %d/%d)，重新取得",
                            attempt,
                            _MAX_CAPTCHA_RETRIES,
                        )
                        page_resp = client.get(url)
                        page_resp.raise_for_status()
                        _validate_url(str(page_resp.url), context="redirect target")
                    else:
                        raise FetchError(
                            self.bank_code,
                            f"CAPTCHA 辨識失敗，已重試 {_MAX_CAPTCHA_RETRIES} 次",
                        )

        # Should not reach here
        raise FetchError(self.bank_code, "PDF 下載流程異常終止")  # pragma: no cover

    def _extract_download_url(self, html_body: str) -> str:
        """Extract the bill download URL from the email HTML."""
        soup = BeautifulSoup(html_body, "html.parser")
        pattern = re.compile(_DOWNLOAD_LINK_TEXT)
        link = soup.find("a", string=pattern)  # type: ignore[call-overload]
        if link is None or not link.get("href"):
            raise FetchError(self.bank_code, "找不到帳單下載連結")
        url = str(link["href"])
        _validate_url(url, context="download URL")
        return url

    def _attempt_download(
        self,
        client: Any,
        page_response: Any,
        national_id: str,
        roc_birthday: str,
        attempt: int,
    ) -> bytes:
        """Attempt a single CAPTCHA-protected download cycle.

        Raises:
            _CaptchaFailedError: CAPTCHA verification failed (caller should retry).
            FetchError: Non-retryable error.
        """
        soup = BeautifulSoup(page_response.text, "html.parser")

        captcha_img = soup.find(
            "img",
            {"id": re.compile(r"captcha", re.I)},  # type: ignore[dict-item]
        )
        if captcha_img is None:
            captcha_img = soup.find(
                "img",
                {"alt": re.compile(r"驗證碼|captcha", re.I)},  # type: ignore[dict-item]
            )

        if captcha_img is None:
            raise FetchError(self.bank_code, "找不到 CAPTCHA 圖片")

        captcha_url = str(captcha_img.get("src", ""))
        if not captcha_url.startswith("http"):
            captcha_url = urljoin(str(page_response.url), captcha_url)
        _validate_url(captcha_url, context="CAPTCHA image URL")

        captcha_resp = client.get(captcha_url)
        captcha_resp.raise_for_status()

        captcha_text = solve_captcha(captcha_resp.content)
        if not captcha_text:
            raise _CaptchaFailedError

        form = soup.find("form")
        if form is None:
            raise FetchError(self.bank_code, "找不到下載表單")

        action_url = str(form.get("action", ""))
        if not action_url.startswith("http"):
            action_url = urljoin(str(page_response.url), action_url)
        _validate_url(action_url, context="form action URL")

        form_data = self._build_form_data(form, national_id, roc_birthday, captcha_text)

        resp = client.post(action_url, data=form_data)
        resp.raise_for_status()
        _validate_url(str(resp.url), context="POST response URL")

        content_type = resp.headers.get("content-type", "")
        if "pdf" in content_type.lower() or resp.content[:4] == b"%PDF":
            return resp.content

        logger.warning(
            "CAPTCHA 嘗試 %d：回應非 PDF (content-type: %s)",
            attempt,
            content_type,
        )
        raise _CaptchaFailedError

    @staticmethod
    def _build_form_data(
        form: Any,
        national_id: str,
        roc_birthday: str,
        captcha_text: str,
    ) -> dict[str, str]:
        """Build form submission data from HTML form fields.

        Strategy: first match fields by common name patterns,
        then fall back to positional assignment for unmatched text inputs.
        """
        data: dict[str, str] = {}

        # Collect hidden fields
        for hidden in form.find_all("input", {"type": "hidden"}):
            name = hidden.get("name")
            if name:
                data[name] = hidden.get("value", "")

        # Fill in known fields by common name patterns
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            if not name:
                continue
            name_lower = name.lower()
            if (
                "id" in name_lower
                and "national" in name_lower
                or name_lower in ("idno", "id_no", "nationalid")
            ):
                data[name] = national_id
            elif "birth" in name_lower or "birthday" in name_lower:
                data[name] = roc_birthday
            elif (
                "captcha" in name_lower
                or "verify" in name_lower
                or "vcode" in name_lower
            ):
                data[name] = captcha_text

        # Fallback: positional assignment for unmatched text inputs
        text_inputs = [
            inp
            for inp in form.find_all("input")
            if inp.get("type", "text") in ("text", "password", "")
            and inp.get("name")
            and inp.get("name") not in data
        ]

        values = [national_id, roc_birthday, captcha_text]
        for inp, val in zip(text_inputs, values, strict=False):
            name = inp.get("name")
            if name and name not in data:
                data[name] = val

        return data


# Module-level registration
fetcher_registry.register(FubonFetcher())
