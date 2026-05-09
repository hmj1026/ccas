"""PipelineSummary 結構測試。"""

from ccas.pipeline.summary import FailedItem, PipelineSummary, StageSummary


class TestPipelineSummary:
    def test_summary_is_frozen(self):
        summary = PipelineSummary(stages=(), total_seconds=1.0)
        assert summary.stages == ()
        assert summary.total_seconds == 1.0
        assert summary.failures == ()

    def test_stage_summary_structure(self):
        ss = StageSummary(stage="ingest", counts={"staged": 3, "failed": 1})
        assert ss.stage == "ingest"
        assert ss.counts["staged"] == 3

    def test_failed_item_structure(self):
        item = FailedItem(item_id="ingest:0", error="test error")
        assert item.item_id == "ingest:0"
        assert item.error == "test error"
