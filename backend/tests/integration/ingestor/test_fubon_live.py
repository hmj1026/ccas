"""Live FUBON web-fetch integration test.

Hits the real Taipei Fubon SPA JSON API and a real Gmail inbox. Opt-in
only — marked ``live_fubon`` and excluded from the default pytest run
via ``addopts = -m 'not live_fubon'`` in ``pyproject.toml``.

Run explicitly::

    uv run pytest tests/integration/ingestor/test_fubon_live.py \\
        -m live_fubon -v -s

Preconditions:
    * ``FUBON_NATIONAL_ID`` and ``FUBON_ROC_BIRTHDAY`` env vars set
    * ``credentials.json`` + ``token.json`` present at paths configured
      by ``Settings``
    * A recent (un-expired) FUBON bill email exists in the Gmail inbox
      matching the ``from:rs@cf.taipeifubon.com.tw`` filter

The test mirrors the production ``job.py`` call path: load Gmail
creds → search → pick newest html-body message → call
``fetcher.fetch_pdf(html_body, credentials)`` via ``asyncio.to_thread``
(matching the real orchestrator). Asserts PDF magic header, opens with
``pikepdf`` using ``national_id`` as password, and checks ``len(pages)
> 0``.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pikepdf
import pytest

from ccas.config import get_settings
from ccas.ingestor.auth import load_credentials
from ccas.ingestor.fetcher.banks.fubon import FubonFetcher
from ccas.ingestor.gmail_client import build_gmail_service, search_messages

_FUBON_GMAIL_FILTER = (
    "from:rs@cf.taipeifubon.com.tw subject:台北富邦銀行 subject:信用卡帳單"
)


def _require_env_or_skip() -> tuple[str, str]:
    """Skip the test if FUBON credentials or Gmail OAuth files are missing."""
    settings = get_settings()
    national_id = settings.get_bank_credential("FUBON", "NATIONAL_ID") or ""
    roc_birthday = settings.get_bank_credential("FUBON", "ROC_BIRTHDAY") or ""
    if not national_id or not roc_birthday:
        pytest.skip(
            "FUBON_NATIONAL_ID / FUBON_ROC_BIRTHDAY not set — "
            "live_fubon test requires real credentials"
        )
    for label, path in (
        ("credentials.json", Path(settings.gmail_credentials_path)),
        ("token.json", Path(settings.gmail_token_path)),
    ):
        if not path.exists():
            pytest.skip(
                f"Gmail OAuth file missing ({label} at {path}); run the "
                "one-time OAuth flow first"
            )
    return national_id, roc_birthday


@pytest.mark.live_fubon
async def test_live_end_to_end() -> None:
    """Download a real FUBON bill PDF end-to-end and verify it opens."""
    national_id, roc_birthday = _require_env_or_skip()
    settings = get_settings()

    creds = load_credentials(
        settings.gmail_credentials_path,
        settings.gmail_token_path,
    )
    service = build_gmail_service(creds)
    messages = await asyncio.to_thread(
        search_messages, service, _FUBON_GMAIL_FILTER
    )
    html_messages = [m for m in messages if m.html_body]
    if not html_messages:
        pytest.skip(
            "no FUBON bill email with html_body found in inbox — cannot "
            "run live test without a fresh download link"
        )
    html_messages.sort(key=lambda m: m.message_date, reverse=True)
    latest = html_messages[0]
    assert latest.html_body is not None

    fetcher = FubonFetcher()
    assert fetcher.can_fetch(latest.html_body), (
        "FubonFetcher.can_fetch rejected the latest inbox email — "
        "gmail_filter may have drifted from the fetcher allowlist"
    )

    credentials = {
        "national_id": national_id,
        "roc_birthday": roc_birthday,
    }
    pdf_bytes = await asyncio.to_thread(
        fetcher.fetch_pdf, latest.html_body, credentials
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF"), (
        f"response is not a PDF (first 16 bytes: {pdf_bytes[:16]!r})"
    )

    with pikepdf.open(io.BytesIO(pdf_bytes), password=national_id) as pdf:
        assert len(pdf.pages) > 0, "PDF opened but has zero pages"
