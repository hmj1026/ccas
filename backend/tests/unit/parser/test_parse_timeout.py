"""parse 階段對毒藥 PDF 的逾時隔離測試。

單筆 PDF 解析若無限阻塞（pdfplumber on a poison PDF），asyncio.wait_for 應
逾時並把該附件標記 PARSE_FAILED，讓 event loop 得以繼續處理下一筆。
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ccas.parser.job import ParseSummary, _process_attachment
from ccas.storage.models import StagedAttachmentStatus


async def test_parse_timeout_marks_attachment_failed() -> None:
    attachment = MagicMock(
        bank_code="CTBC",
        staged_path="CTBC/bill.pdf",
        original_filename="bill.pdf",
    )
    session = AsyncMock()
    summary = ParseSummary()

    # The fixture timeout (0.05s) must stay below the block bound; the leaked
    # parse thread is released by the test after the call so it exits promptly
    # instead of imposing a fixed wall-clock floor on the suite.
    release = threading.Event()

    def _slow_parse(_candidates: object, _path: object) -> tuple[bool, object, str]:
        # Block (poison-PDF stand-in) until released; bounded so a regression
        # of the timeout path can never hang the test.
        release.wait(timeout=5.0)
        return True, MagicMock(), ""

    settings = MagicMock(
        staging_dir="./data/staging",
        pdf_parse_timeout_seconds=0.05,
    )

    try:
        with (
            patch("ccas.parser.job.get_settings", return_value=settings),
            patch(
                "ccas.parser.job.resolve_staged_path",
                return_value=Path("/tmp/CTBC/bill.pdf"),
            ),
            patch("ccas.parser.job.registry.resolve", return_value=[MagicMock()]),
            patch("ccas.parser.job._try_parse", new=_slow_parse),
            patch(
                "ccas.parser.job.update_attachment_status", new=AsyncMock()
            ) as status_mock,
        ):
            await _process_attachment(attachment, session, summary, None)
    finally:
        release.set()  # let the leaked background thread finish

    assert summary.failed_count == 1
    assert status_mock.await_count == 1
    call = status_mock.await_args
    assert call is not None
    assert call.kwargs["status"] == StagedAttachmentStatus.PARSE_FAILED
    assert any("逾時" in err for err in summary.errors)
