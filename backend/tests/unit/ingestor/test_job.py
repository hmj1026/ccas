"""``ccas.ingestor.job`` 的單元測試。

聚焦既有測試未涵蓋的區塊：

* ``_fetch_active_banks`` / ``_apply_bank_settings_filter`` 的 DB 過濾鏈。
* ``_build_gmail_query`` 的日期子句組合。
* ``_cleanup_old_staged_file`` 的逃逸防護與刪檔。
* ``_process_attachment`` 的黑名單跳過。
* ``_process_web_fetch`` 的完整 web-fetch 流程（成功 / 重試 / 過期 / 失敗）。
* ``run_ingestion_job`` 的無啟用銀行、搜尋失敗、舊檔清理與 rollback 分支。
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.ingestor.fetcher.base import BankFetcher
from ccas.ingestor.gmail_client import GmailAttachmentMeta, GmailMessage
from ccas.ingestor.job import (
    IngestionSummary,
    _apply_bank_settings_filter,
    _build_gmail_query,
    _cleanup_old_staged_file,
    _fetch_active_banks,
    _process_attachment,
    _process_web_fetch,
    run_ingestion_job,
)
from ccas.shared.pipeline_types import PipelineOptions
from ccas.storage.models import BankConfig, BankSettings, Base


# --------------------------------------------------------------------------- #
# Shared fakes / fixtures
# --------------------------------------------------------------------------- #
class FakeFetcher(BankFetcher):
    """測試用 ``BankFetcher`` 假件，繼承 ABC 以符合 nominal typing。"""

    def __init__(
        self,
        *,
        can: bool = True,
        pdf: bytes = b"%PDF-1.4 fake",
        error: Exception | None = None,
    ) -> None:
        self._can = can
        self._pdf = pdf
        self._error = error

    @property
    def bank_code(self) -> str:
        return "FUBON"

    def can_fetch(self, html_body: str) -> bool:
        return self._can

    def fetch_pdf(self, html_body: str, credentials: dict[str, str]) -> bytes:
        if self._error is not None:
            raise self._error
        return self._pdf


@pytest.fixture
def summary() -> IngestionSummary:
    return IngestionSummary()


@pytest.fixture
def web_message() -> GmailMessage:
    return GmailMessage(
        message_id="web-msg-1",
        message_date=datetime(2026, 3, 15),
        pdf_attachments=(),
        html_body="<html>fubon statement</html>",
    )


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


# --------------------------------------------------------------------------- #
# _fetch_active_banks / _apply_bank_settings_filter
# --------------------------------------------------------------------------- #
class TestFetchActiveBanks:
    async def test_filters_inactive_empty_filter_and_disabled(self) -> None:
        """只回傳 is_active=True、gmail_filter 非空、且未被 settings 停用的銀行。"""
        engine, factory = await _make_db()
        async with factory() as session:
            session.add_all(
                [
                    BankConfig(
                        bank_code="CTBC",
                        bank_name="CTBC",
                        gmail_filter="from:ctbc",
                        is_active=True,
                    ),
                    BankConfig(
                        bank_code="FUBON",
                        bank_name="Fubon",
                        gmail_filter="from:fubon",
                        is_active=True,
                    ),
                    BankConfig(
                        bank_code="EMPTY",
                        bank_name="Empty",
                        gmail_filter="",
                        is_active=True,
                    ),
                    BankConfig(
                        bank_code="OFF",
                        bank_name="Off",
                        gmail_filter="from:off",
                        is_active=False,
                    ),
                    # FUBON 被 bank_settings.enabled=False 停用。
                    BankSettings(code="FUBON", enabled=False),
                ]
            )
            await session.commit()

            banks = await _fetch_active_banks(session, None)
            codes = {b.bank_code for b in banks}
            assert codes == {"CTBC"}
        await engine.dispose()

    async def test_bank_code_option_narrows_result(self) -> None:
        """options.bank_code 僅回傳該銀行。"""
        engine, factory = await _make_db()
        async with factory() as session:
            session.add_all(
                [
                    BankConfig(
                        bank_code="CTBC",
                        bank_name="CTBC",
                        gmail_filter="from:ctbc",
                        is_active=True,
                    ),
                    BankConfig(
                        bank_code="ESUN",
                        bank_name="ESun",
                        gmail_filter="from:esun",
                        is_active=True,
                    ),
                ]
            )
            await session.commit()

            banks = await _fetch_active_banks(
                session, PipelineOptions(bank_code="ESUN")
            )
            assert [b.bank_code for b in banks] == ["ESUN"]
        await engine.dispose()

    async def test_empty_configs_short_circuits(self) -> None:
        """無符合的 config 時 ``_apply_bank_settings_filter`` 直接回傳空列表。"""
        engine, factory = await _make_db()
        async with factory() as session:
            result = await _apply_bank_settings_filter(session, [])
            assert result == []
        await engine.dispose()


# --------------------------------------------------------------------------- #
# _build_gmail_query
# --------------------------------------------------------------------------- #
class TestBuildGmailQuery:
    def test_no_options_returns_base(self) -> None:
        assert _build_gmail_query("from:ctbc", None) == "from:ctbc"

    def test_no_date_clause_returns_base(self) -> None:
        # 無 year/month → gmail_date_filter() 為空字串。
        assert _build_gmail_query("from:ctbc", PipelineOptions()) == "from:ctbc"

    def test_appends_date_clause(self) -> None:
        result = _build_gmail_query("from:ctbc", PipelineOptions(year=2026, month=3))
        assert result.startswith("from:ctbc ")
        assert "after:" in result and "before:" in result


# --------------------------------------------------------------------------- #
# _cleanup_old_staged_file
# --------------------------------------------------------------------------- #
class TestCleanupOldStagedFile:
    async def test_none_path_is_noop(self) -> None:
        with patch("ccas.ingestor.job.resolve_staged_path") as mock_resolve:
            await _cleanup_old_staged_file("/staging", None)
            mock_resolve.assert_not_called()

    async def test_escape_path_logs_warning_and_skips(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch(
                "ccas.ingestor.job.resolve_staged_path",
                side_effect=ValueError("escape"),
            ),
            caplog.at_level(logging.WARNING, logger="ccas.ingestor.job"),
        ):
            await _cleanup_old_staged_file("/staging", "../../etc/passwd")
        assert "逃逸" in caplog.text

    async def test_existing_file_is_unlinked(self, tmp_path) -> None:
        target = tmp_path / "old.pdf"
        target.write_bytes(b"stale")
        with patch("ccas.ingestor.job.resolve_staged_path", return_value=target):
            await _cleanup_old_staged_file(str(tmp_path), "old.pdf")
        assert not target.exists()

    async def test_missing_file_is_noop(self, tmp_path) -> None:
        target = tmp_path / "ghost.pdf"
        with patch("ccas.ingestor.job.resolve_staged_path", return_value=target):
            # 不存在 → 不應 raise。
            await _cleanup_old_staged_file(str(tmp_path), "ghost.pdf")
        assert not target.exists()


# --------------------------------------------------------------------------- #
# _process_attachment: blacklist skip
# --------------------------------------------------------------------------- #
class TestProcessAttachmentBlacklist:
    @patch("ccas.ingestor.job.should_skip_attachment", return_value=True)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    async def test_blacklisted_filename_is_skipped(
        self, mock_find, mock_skip, summary
    ) -> None:
        attachment = GmailAttachmentMeta(
            message_id="m1",
            attachment_id="a1",
            filename="ad-banner.pdf",
            message_date=datetime(2026, 3, 15),
            size=10,
        )
        result = await _process_attachment(
            AsyncMock(), MagicMock(), "CTBC", attachment, "/staging", summary
        )
        assert result is None
        assert summary.skipped_count == 1
        # 命中黑名單即返回，不查 DB。
        mock_find.assert_not_called()


# --------------------------------------------------------------------------- #
# _process_web_fetch
# --------------------------------------------------------------------------- #
class TestProcessWebFetch:
    async def test_no_fetcher_returns_none(self, web_message, summary) -> None:
        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = None
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )
        assert result is None

    async def test_cannot_fetch_returns_none(self, web_message, summary) -> None:
        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher(can=False)
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )
        assert result is None

    @patch("ccas.ingestor.job.backfill_part_id", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    async def test_existing_staged_not_force_is_skipped(
        self, mock_find, mock_backfill, web_message, summary
    ) -> None:
        existing = MagicMock(status="staged")
        mock_find.return_value = existing
        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher()
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )
        assert result is None
        assert summary.skipped_count == 1
        mock_backfill.assert_awaited_once()

    @patch("ccas.ingestor.job.staged_path_for_storage", return_value="new/stored.pdf")
    @patch("ccas.ingestor.job.atomic_write_bytes")
    @patch("ccas.ingestor.job.build_staged_path")
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.resolve_bank_credential", new_callable=AsyncMock)
    async def test_success_creates_staged_record(
        self,
        mock_cred,
        mock_find,
        mock_create,
        mock_build,
        mock_write,
        mock_storage,
        web_message,
        summary,
    ) -> None:
        mock_cred.return_value = ""
        mock_find.return_value = None
        mock_path = MagicMock()
        mock_path.parent = MagicMock()
        mock_build.return_value = mock_path

        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher(pdf=b"%PDF data")
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )

        assert result is None  # 無既有記錄 → 無舊檔需清理
        assert summary.staged_count == 1
        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["source_type"] == "web_fetch"

    @patch("ccas.ingestor.job.staged_path_for_storage", return_value="new/stored.pdf")
    @patch("ccas.ingestor.job.atomic_write_bytes")
    @patch("ccas.ingestor.job.build_staged_path")
    @patch("ccas.ingestor.job.delete_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.resolve_bank_credential", new_callable=AsyncMock)
    async def test_failed_retry_replaces_and_returns_old_path(
        self,
        mock_cred,
        mock_find,
        mock_create,
        mock_delete,
        mock_build,
        mock_write,
        mock_storage,
        web_message,
        summary,
    ) -> None:
        mock_cred.return_value = ""
        existing = MagicMock(status="failed", staged_path="old/stored.pdf")
        mock_find.return_value = existing
        mock_path = MagicMock()
        mock_path.parent = MagicMock()
        mock_build.return_value = mock_path

        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher()
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )

        # 舊路徑 != 新路徑 → 回傳供 commit 後清理。
        assert result == "old/stored.pdf"
        mock_delete.assert_awaited_once()
        assert summary.staged_count == 1

    @patch("ccas.ingestor.job.build_staged_path")
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.resolve_bank_credential", new_callable=AsyncMock)
    async def test_expired_marker_sets_fetch_expired(
        self,
        mock_cred,
        mock_find,
        mock_create,
        mock_build,
        web_message,
        summary,
    ) -> None:
        mock_cred.return_value = ""
        mock_find.return_value = None
        mock_path = MagicMock()
        mock_path.parent = MagicMock()
        mock_build.return_value = mock_path
        err = RuntimeError("record_not_found: serial consumed")

        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher(error=err)
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )

        assert result is None
        # 過期視為 skip，不計入 failed。
        assert summary.skipped_count == 1
        assert summary.failed_count == 0
        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["status"].value == "fetch_expired"

    @patch("ccas.ingestor.job.build_staged_path")
    @patch("ccas.ingestor.job.create_staged_record", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.resolve_bank_credential", new_callable=AsyncMock)
    async def test_generic_failure_creates_failed_record(
        self,
        mock_cred,
        mock_find,
        mock_create,
        mock_build,
        web_message,
        summary,
    ) -> None:
        mock_cred.return_value = ""
        mock_find.return_value = None
        mock_path = MagicMock()
        mock_path.parent = MagicMock()
        mock_build.return_value = mock_path

        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher(error=RuntimeError("boom"))
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )

        assert result is None
        assert summary.failed_count == 1
        assert any("Web-fetch 失敗" in e for e in summary.errors)
        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["status"].value == "failed"

    @patch("ccas.ingestor.job.update_staged_record_failure", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.build_staged_path")
    @patch("ccas.ingestor.job.find_existing_staged", new_callable=AsyncMock)
    @patch("ccas.ingestor.job.resolve_bank_credential", new_callable=AsyncMock)
    async def test_failure_with_existing_updates_record(
        self,
        mock_cred,
        mock_find,
        mock_build,
        mock_update,
        web_message,
        summary,
    ) -> None:
        mock_cred.return_value = ""
        existing = MagicMock(status="failed", staged_path="old/stored.pdf")
        mock_find.return_value = existing
        mock_path = MagicMock()
        mock_path.parent = MagicMock()
        mock_build.return_value = mock_path

        with patch("ccas.ingestor.fetcher.fetcher_registry") as mock_reg:
            mock_reg.get.return_value = FakeFetcher(error=RuntimeError("boom"))
            result = await _process_web_fetch(
                AsyncMock(), "FUBON", web_message, "/staging", MagicMock(), summary
            )

        assert result is None
        mock_update.assert_awaited_once()
        assert summary.failed_count == 1


# --------------------------------------------------------------------------- #
# run_ingestion_job orchestration
# --------------------------------------------------------------------------- #
class TestRunIngestionJob:
    async def test_no_active_banks_reports_and_returns(self) -> None:
        """無啟用銀行 → 記錄警告、emit total=0、提早返回（reporter=None 走 Noop）。"""
        session = AsyncMock()
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            summary = await run_ingestion_job(session, options=None, reporter=None)

        assert summary.banks_processed == 0
        assert any("未找到任何啟用的銀行設定" in e for e in summary.errors)

    async def test_search_failure_is_recorded_and_continues(self) -> None:
        """Gmail 搜尋拋錯時記錄錯誤並繼續（不中止 batch）。"""
        session = AsyncMock()
        bank = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[bank]),
            ),
            patch(
                "ccas.ingestor.job.search_messages",
                side_effect=RuntimeError("gmail down"),
            ),
        ):
            summary = await run_ingestion_job(session, options=None, reporter=None)

        assert summary.banks_processed == 1
        assert summary.messages_found == 0
        assert any("Gmail 搜尋失敗" in e for e in summary.errors)

    async def test_attachment_old_path_is_cleaned_after_commit(self) -> None:
        """附件成功取代舊記錄 → commit 後清理舊磁碟檔。"""
        session = AsyncMock()
        bank = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
        msg = MagicMock(pdf_attachments=[MagicMock(filename="s.pdf")], html_body=None)
        cleanup = AsyncMock()
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[bank]),
            ),
            patch("ccas.ingestor.job.search_messages", return_value=[msg]),
            patch(
                "ccas.ingestor.job._process_attachment",
                new=AsyncMock(return_value="old/stored.pdf"),
            ),
            patch("ccas.ingestor.job._cleanup_old_staged_file", new=cleanup),
        ):
            summary = await run_ingestion_job(session, options=None, reporter=None)

        session.commit.assert_awaited()
        cleanup.assert_awaited_once()
        assert cleanup.await_args_list[-1].args[1] == "old/stored.pdf"
        assert summary.banks_processed == 1

    async def test_attachment_cleanup_failure_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """舊檔清理失敗只留 orphan、記 warning，不中止 loop。"""
        session = AsyncMock()
        bank = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
        msg = MagicMock(pdf_attachments=[MagicMock(filename="s.pdf")], html_body=None)
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[bank]),
            ),
            patch("ccas.ingestor.job.search_messages", return_value=[msg]),
            patch(
                "ccas.ingestor.job._process_attachment",
                new=AsyncMock(return_value="old/stored.pdf"),
            ),
            patch(
                "ccas.ingestor.job._cleanup_old_staged_file",
                new=AsyncMock(side_effect=OSError("disk")),
            ),
            caplog.at_level(logging.WARNING, logger="ccas.ingestor.job"),
        ):
            await run_ingestion_job(session, options=None, reporter=None)

        assert "orphan left on disk" in caplog.text

    async def test_attachment_item_failure_triggers_rollback(self) -> None:
        """_process_attachment 拋錯 → rollback 並繼續。"""
        session = AsyncMock()
        bank = MagicMock(bank_code="CTBC", gmail_filter="from:ctbc")
        msg = MagicMock(pdf_attachments=[MagicMock(filename="s.pdf")], html_body=None)
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[bank]),
            ),
            patch("ccas.ingestor.job.search_messages", return_value=[msg]),
            patch(
                "ccas.ingestor.job._process_attachment",
                new=AsyncMock(side_effect=RuntimeError("kaboom")),
            ),
        ):
            await run_ingestion_job(session, options=None, reporter=None)

        session.rollback.assert_awaited_once()

    async def test_web_fetch_old_path_is_cleaned_after_commit(self) -> None:
        """web-fetch 成功取代舊記錄 → commit 後清理舊檔。"""
        session = AsyncMock()
        bank = MagicMock(bank_code="FUBON", gmail_filter="from:fubon")
        msg = MagicMock(pdf_attachments=[], html_body="<html>fubon</html>")
        cleanup = AsyncMock()
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[bank]),
            ),
            patch("ccas.ingestor.job.search_messages", return_value=[msg]),
            patch(
                "ccas.ingestor.job._process_web_fetch",
                new=AsyncMock(return_value="old/web.pdf"),
            ),
            patch("ccas.ingestor.job._cleanup_old_staged_file", new=cleanup),
        ):
            summary = await run_ingestion_job(session, options=None, reporter=None)

        session.commit.assert_awaited()
        cleanup.assert_awaited_once()
        assert cleanup.await_args_list[-1].args[1] == "old/web.pdf"
        assert summary.messages_found == 1

    async def test_web_fetch_item_failure_triggers_rollback(self) -> None:
        """_process_web_fetch 拋錯 → rollback 並繼續。"""
        session = AsyncMock()
        bank = MagicMock(bank_code="FUBON", gmail_filter="from:fubon")
        msg = MagicMock(pdf_attachments=[], html_body="<html>fubon</html>")
        with (
            patch("ccas.ingestor.job.load_credentials", return_value=MagicMock()),
            patch("ccas.ingestor.job.build_gmail_service", return_value=MagicMock()),
            patch(
                "ccas.ingestor.job._fetch_active_banks",
                new=AsyncMock(return_value=[bank]),
            ),
            patch("ccas.ingestor.job.search_messages", return_value=[msg]),
            patch(
                "ccas.ingestor.job._process_web_fetch",
                new=AsyncMock(side_effect=RuntimeError("kaboom")),
            ),
        ):
            await run_ingestion_job(session, options=None, reporter=None)

        session.rollback.assert_awaited_once()
