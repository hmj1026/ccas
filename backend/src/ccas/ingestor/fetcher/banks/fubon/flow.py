"""FUBON download pipeline orchestration.

This module wires together ``FubonClient`` + ``captcha`` (+ optional
``captcha_llm``) into the end-to-end flow described in the impl design:

    email_html → serial_key → open_spa → loop[captcha → ocr → do_login] →
    get_main_info → get_bill_pdf → PDF bytes

All internal errors (``FubonFlowError`` subclasses) are remapped to the
project-wide ``FetchError`` at the flow boundary so callers only see the
public contract. Reason slugs are embedded in the ``FetchError`` message so
tests and pipeline summary logs can match on them.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ccas.ingestor.fetcher.banks.fubon import captcha, captcha_llm
from ccas.ingestor.fetcher.banks.fubon.client import ALLOWED_SPA_HOST, FubonClient
from ccas.ingestor.fetcher.banks.fubon.errors import (
    FubonFlowError,
    FubonLoginError,
)
from ccas.ingestor.fetcher.base import FetchError

logger = logging.getLogger(__name__)

_BANK = "FUBON"


def _extract_serial_key(email_html: str) -> str:
    """Pull the 32-char serial key from an email HTML body.

    Accepts both raw `/<serial>` and `/client/pdf/<serial>` link forms.
    """
    soup = BeautifulSoup(email_html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", ""))
        try:
            parsed = urlparse(href)
        except ValueError:
            continue
        if parsed.hostname != ALLOWED_SPA_HOST:
            continue
        path = parsed.path.strip("/")
        if path.startswith("client/pdf/"):
            path = path[len("client/pdf/") :]
        if path:
            return path.split("/")[0]
    raise FetchError(_BANK, "no_download_link: FUBON bill link not found in email")


async def download(
    *,
    email_html: str,
    id_number: str,
    birthday: str,
    max_retries: int = 7,
    llm_fallback: bool = False,
    llm_api_key: str | None = None,
) -> bytes:
    """Run the full FUBON download pipeline and return PDF bytes.

    Callers must pre-validate ``id_number`` / ``birthday``; this function
    assumes non-empty strings and does not re-check them.
    """
    serial_key = _extract_serial_key(email_html)

    try:
        async with FubonClient() as client:
            await client.open_spa(serial_key=serial_key)
            await _login_with_captcha_retry(
                client=client,
                id_number=id_number,
                birthday=birthday,
                serial_key=serial_key,
                max_retries=max_retries,
                llm_fallback=llm_fallback,
                llm_api_key=llm_api_key,
            )
            main_info = await client.get_main_info()
            return await client.get_bill_pdf(
                bill_period=str(main_info["billPeriod"]),
                batch_period=str(main_info["batchPeriod"]),
                uid=str(main_info["uniqueIdentifier"]),
                tw_year_month=str(main_info["twYearMonth"]),
            )
    except FetchError:
        raise
    except FubonFlowError as exc:
        raise FetchError(_BANK, f"flow_error: {exc}") from exc


async def _login_with_captcha_retry(
    *,
    client: FubonClient,
    id_number: str,
    birthday: str,
    serial_key: str,
    max_retries: int,
    llm_fallback: bool,
    llm_api_key: str | None,
) -> None:
    """Loop: fetch captcha → OCR (→ LLM) → do_login, retry on rejection."""
    # Fail-loud pre-check: if the user advertised fallback=True but did not
    # supply a key, the previous silent-downgrade behaviour resulted in a
    # ``captcha_retry_exhausted`` error with no hint about the real cause.
    # Surface the misconfiguration immediately.
    if llm_fallback and not llm_api_key:
        raise FetchError(
            _BANK,
            "llm_fallback_unavailable: FUBON_CAPTCHA_FALLBACK_LLM=true "
            "but no API key provided",
        )
    llm_enabled = llm_fallback and bool(llm_api_key)

    for attempt in range(1, max_retries + 1):
        server_token, jpeg = await client.get_captcha()
        result = captcha.solve(jpeg)

        if result is not None:
            answer = result.text
        elif llm_enabled:
            assert llm_api_key is not None  # guarded by llm_enabled
            try:
                answer = await captcha_llm.solve_with_llm(jpeg, api_key=llm_api_key)
            except captcha_llm.CaptchaLlmUnavailableError as exc:
                # Infrastructure / config problem that will not be fixed by
                # retrying — fail loud so operators see the real cause
                # instead of a misleading ``captcha_retry_exhausted``.
                raise FetchError(
                    _BANK,
                    f"llm_fallback_unavailable: {exc}",
                ) from exc
            except captcha_llm.CaptchaLlmRejectedError as exc:
                logger.debug(
                    "fubon_captcha_llm_rejected",
                    extra={"attempt": attempt, "error": str(exc)},
                )
                continue
        else:
            logger.debug("fubon_captcha_ocr_rejected", extra={"attempt": attempt})
            continue

        try:
            await client.do_login(
                id_number=id_number,
                birthday=birthday,
                serial_key=serial_key,
                captcha_answer=answer,
                server_token=server_token,
            )
        except FubonLoginError as exc:
            if exc.code == "captcha_wrong":
                logger.debug(
                    "fubon_captcha_wrong_retry",
                    extra={"attempt": attempt, "raw_code": exc.raw_code},
                )
                continue
            if exc.code == "record_not_found":
                # Stale/expired serial_key or already-fetched bill: this is
                # a soft skip, not a credential failure. Surface a distinct
                # reason so operators are not directed to fix ID/birthday.
                raise FetchError(
                    _BANK,
                    f"record_not_found: doLogin msg={exc.raw_message!r}",
                ) from exc
            raise FetchError(
                _BANK,
                f"credentials_wrong: doLogin code={exc.code} "
                f"raw={exc.raw_code} msg={exc.raw_message!r}",
            ) from exc
        return

    raise FetchError(
        _BANK,
        f"captcha_retry_exhausted: {max_retries} attempts failed",
    )
