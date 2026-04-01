"""Unit tests for pipeline filter helper."""

from sqlalchemy import select

from ccas.pipeline.filters import apply_pipeline_filters
from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import StagedAttachment


class TestApplyPipelineFilters:
    def _base_stmt(self):
        return select(StagedAttachment).where(StagedAttachment.status == "staged")

    def test_none_options_returns_unchanged(self):
        stmt = self._base_stmt()
        result = apply_pipeline_filters(stmt, None)
        # Should be the same statement object
        assert str(result.compile()) == str(stmt.compile())

    def test_default_options_returns_unchanged(self):
        stmt = self._base_stmt()
        opts = PipelineOptions()
        result = apply_pipeline_filters(stmt, opts)
        assert str(result.compile()) == str(stmt.compile())

    def test_bank_code_adds_filter(self):
        stmt = self._base_stmt()
        opts = PipelineOptions(bank_code="CTBC")
        result = apply_pipeline_filters(stmt, opts)
        compiled = str(result.compile())
        assert "bank_code" in compiled

    def test_year_month_adds_date_filter(self):
        stmt = self._base_stmt()
        opts = PipelineOptions(year=2026, month=3)
        result = apply_pipeline_filters(stmt, opts)
        compiled = str(result.compile())
        assert "message_date" in compiled

    def test_bank_and_date_adds_both_filters(self):
        stmt = self._base_stmt()
        opts = PipelineOptions(bank_code="CTBC", year=2026, month=3)
        result = apply_pipeline_filters(stmt, opts)
        compiled = str(result.compile())
        assert "bank_code" in compiled
        assert "message_date" in compiled

    def test_force_only_does_not_add_filters(self):
        stmt = self._base_stmt()
        opts = PipelineOptions(force=True)
        result = apply_pipeline_filters(stmt, opts)
        assert str(result.compile()) == str(stmt.compile())
