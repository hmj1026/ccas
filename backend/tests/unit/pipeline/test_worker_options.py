"""Worker run_pipeline_sync options deserialization tests."""

from ccas.pipeline.options import PipelineOptions


class TestWorkerOptionsDeserialization:
    def test_from_dict_none_returns_defaults(self):
        result = PipelineOptions.from_dict(None)
        assert result == PipelineOptions()

    def test_from_dict_empty_returns_defaults(self):
        result = PipelineOptions.from_dict({})
        assert result == PipelineOptions()

    def test_from_dict_with_all_opts(self):
        opts = {"force": True, "bank_code": "CTBC", "year": 2026, "month": 3}
        result = PipelineOptions.from_dict(opts)
        assert result == PipelineOptions(
            force=True, bank_code="CTBC", year=2026, month=3
        )

    def test_from_dict_partial_opts(self):
        opts = {"force": True}
        result = PipelineOptions.from_dict(opts)
        assert result.force is True
        assert result.bank_code is None

    def test_to_dict_round_trip(self):
        original = PipelineOptions(force=True, bank_code="ESUN", year=2025, month=12)
        restored = PipelineOptions.from_dict(original.to_dict())
        assert restored == original
