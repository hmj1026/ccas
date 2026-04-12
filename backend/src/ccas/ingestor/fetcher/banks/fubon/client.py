"""HTTPX async wrapper around the FUBON SPA JSON API.

Responsibilities:
    * Follow the initial 302 redirect from the email's serial-key link to the
      SPA entry at ``/client/pdf/<serial>``, collecting session cookies.
    * Reject any redirect that escapes the ``fbmbill.taipeifubon.com.tw``
      host (defence in depth on top of the fetcher's url allowlist).
    * Fetch a stateless captcha (``<server_token>,<base64_jpeg>``) and split
      it into usable pieces.
    * POST ``/doLogin`` with the captcha answer, store the returned JWT +
      bill main-info, and classify error responses via the ``errorMsg``
      string returned by the backend.
    * GET ``/PDFReportProc`` with the JWT injected via the raw
      ``Authorization`` header (NOT ``Bearer``, matching the SPA's request
      interceptor).

Response-schema note:

    doLogin success::

        {"errorMsg": null, "jwt": "<jwt>",
         "billPeriod": "...", "twYearMonth": "...",
         "batchPeriod": "...", "uniqueIdentifier": "...",
         "months": [...], ...}

    doLogin failure::

        {"errorMsg": "登入失敗, 請確認圖形驗證碼是否輸入正確",
         "jwt": null, ...everything-else-null...}

Success is signalled by ``jwt`` being a non-empty string. Failures are
classified by keyword-matching ``errorMsg`` (see ``_classify_error_msg``)
into the same ``captcha_wrong`` / ``id_wrong`` / ``birthday_wrong`` /
``unknown`` slugs that ``flow.py`` already understands — the classification
surface is unchanged, only the wire parsing moved. Unknown errorMsgs
collapse to ``"unknown"`` so the flow layer burns a retry slot and surfaces
the raw message in logs for future mapping updates.
"""

from __future__ import annotations

import base64
import binascii
import logging
from types import TracebackType
from typing import Any

import httpx

from ccas.ingestor.fetcher.banks.fubon.errors import (
    FubonLoginError,
    FubonRedirectError,
    FubonSessionError,
)

logger = logging.getLogger(__name__)

ALLOWED_SPA_HOST = "fbmbill.taipeifubon.com.tw"
_BASE_URL = f"https://{ALLOWED_SPA_HOST}"
_DEFAULT_TIMEOUT = 15.0

_MAIN_INFO_FIELDS: tuple[str, ...] = (
    "billPeriod",
    "twYearMonth",
    "batchPeriod",
    "uniqueIdentifier",
)


def _classify_error_msg(error_msg: str) -> str:
    """Map a FUBON ``errorMsg`` string to an error slug.

    Keyword-based because the backend does not expose a stable numeric
    code. Keep match patterns broad — the SPA chunks show the server
    localises messages but the keywords are stable. Unknown strings map
    to ``"unknown"`` so the flow layer treats them as non-captcha and
    burns a retry slot rather than looping forever.

    ``record_not_found`` covers the live-observed ``登入失敗, 查無資料``
    reply that FUBON returns for expired / already-consumed serial keys
    (see ``docs/e2e-user-guide-walkthrough.md``). Flow layer treats it as
    a soft skip so operators are not mis-directed to fix credentials.
    """
    if not error_msg:
        return "unknown"
    if "驗證碼" in error_msg:
        return "captcha_wrong"
    if "身分證" in error_msg or "身份證" in error_msg:
        return "id_wrong"
    if "出生" in error_msg or "生日" in error_msg:
        return "birthday_wrong"
    if "查無資料" in error_msg or "查無此筆" in error_msg:
        return "record_not_found"
    return "unknown"


class FubonClient:
    """Async HTTP wrapper for the FUBON bill-download SPA API."""

    def __init__(self, *, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            follow_redirects=False,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
            },
        )
        self._jwt: str | None = None
        self._main_info: dict[str, Any] | None = None

    async def __aenter__(self) -> FubonClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def open_spa(self, *, serial_key: str) -> None:
        """Follow the email-link redirect manually, validating each hop."""
        url = f"/{serial_key}"
        for _ in range(5):
            resp = await self._client.get(url)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location", "")
                target = resp.url.join(loc)
                # Explicit allowlist check: reject empty host and any host
                # that is not exactly the FUBON SPA domain. ``target.host``
                # may be empty if the Location header is malformed; treat
                # that as a redirect failure rather than silently proceeding.
                if target.host != ALLOWED_SPA_HOST:
                    raise FubonRedirectError(
                        f"redirect escapes allowlist: host={target.host!r}"
                    )
                url = str(target)
                continue
            if resp.status_code == 200:
                return
            raise FubonSessionError(
                f"unexpected status on SPA open: {resp.status_code}"
            )
        raise FubonSessionError("too many redirects opening SPA")

    async def get_captcha(self) -> tuple[str, bytes]:
        """Fetch a captcha and split ``<token>,<base64_jpeg>``."""
        resp = await self._client.get("/checkImgs/captcha.jpg")
        if resp.status_code != 200:
            raise FubonSessionError(f"captcha http {resp.status_code}")
        body = resp.text.strip()
        if "," not in body:
            raise FubonSessionError("captcha response missing ',' separator")
        token, _, b64 = body.partition(",")
        try:
            jpeg = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FubonSessionError(f"captcha base64 decode failed: {exc}") from exc
        if not jpeg.startswith(b"\xff\xd8\xff"):
            raise FubonSessionError("captcha payload is not a JPEG")
        return token, jpeg

    async def do_login(
        self,
        *,
        id_number: str,
        birthday: str,
        serial_key: str,
        captcha_answer: str,
        server_token: str,
    ) -> None:
        """POST ``/doLogin`` and store the JWT on success."""
        payload = {
            "id": id_number,
            "birthday": birthday,
            "serialKey": serial_key,
            "captchaCode": f"{server_token},{captcha_answer}",
        }
        resp = await self._client.post("/doLogin", json=payload)
        if resp.status_code != 200:
            raise FubonLoginError(
                code="unknown",
                raw_code=resp.status_code,
                message=f"http {resp.status_code}",
            )
        data: dict[str, Any] = resp.json()
        jwt = data.get("jwt")
        if isinstance(jwt, str) and jwt:
            # Cache the main-info fields returned alongside the JWT so
            # ``get_main_info`` can skip the redundant round-trip. Validate
            # presence here — downstream ``get_bill_pdf`` will `str(None)`
            # these into query params if we let missing fields through,
            # producing a silent "None" in the URL instead of a loud error.
            main_info = {field: data.get(field) for field in _MAIN_INFO_FIELDS}
            missing = [f for f, v in main_info.items() if v is None]
            if missing:
                raise FubonSessionError(
                    f"doLogin success but main_info fields missing: {missing}"
                )
            self._jwt = jwt
            self._main_info = main_info
            return
        error_msg = str(data.get("errorMsg") or "")
        slug = _classify_error_msg(error_msg)
        raise FubonLoginError(
            code=slug,
            raw_code=None,
            message=error_msg,
        )

    async def get_main_info(self) -> dict[str, Any]:
        """Return the bill main-info dict cached from ``do_login``.

        The FUBON ``/doLogin`` response already carries the ``billPeriod``,
        ``batchPeriod``, ``uniqueIdentifier`` and ``twYearMonth`` fields, so
        ``do_login`` caches them into ``self._main_info`` and this method
        simply hands them back.
        """
        if self._main_info is None:
            raise RuntimeError("main_info not set; call do_login first")
        return dict(self._main_info)

    async def get_bill_pdf(
        self,
        *,
        bill_period: str,
        batch_period: str,
        uid: str,
        tw_year_month: str,
    ) -> bytes:
        """GET ``/PDFReportProc`` and return PDF bytes."""
        if not self._jwt:
            raise RuntimeError("jwt not set; call do_login first")
        resp = await self._client.get(
            "/PDFReportProc",
            params={
                "billPeriod": bill_period,
                "batchPeriod": batch_period,
                "id": uid,
                "twYearMonth": tw_year_month,
            },
            headers={"Authorization": self._jwt},
        )
        if resp.status_code != 200:
            raise FubonSessionError(f"PDFReportProc http {resp.status_code}")
        content = resp.content
        if not content.startswith(b"%PDF"):
            raise FubonSessionError("PDFReportProc response is not a PDF")
        return content
