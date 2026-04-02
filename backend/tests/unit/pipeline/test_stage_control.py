"""Pipeline stage control tests.

Covers _validate_stage_range() for full range, partial range,
single stage, invalid names, and reversed order.
"""

import pytest

from ccas.pipeline.orchestrator import STAGE_ORDER, _validate_stage_range


class TestStageOrder:
    def test_stage_order_has_five_stages(self):
        assert len(STAGE_ORDER) == 5

    def test_stage_order_sequence(self):
        assert STAGE_ORDER == ("ingest", "decrypt", "parse", "classify", "notify")


class TestValidateStageRange:
    def test_full_range_defaults(self):
        result = _validate_stage_range()
        assert result == STAGE_ORDER

    def test_from_none_to_none(self):
        result = _validate_stage_range(None, None)
        assert result == STAGE_ORDER

    def test_from_first_stage(self):
        result = _validate_stage_range(from_stage="ingest")
        assert result == STAGE_ORDER

    def test_from_middle_stage(self):
        result = _validate_stage_range(from_stage="decrypt")
        assert result == ("decrypt", "parse", "classify", "notify")

    def test_from_last_stage(self):
        result = _validate_stage_range(from_stage="notify")
        assert result == ("notify",)

    def test_to_last_stage(self):
        result = _validate_stage_range(to_stage="notify")
        assert result == STAGE_ORDER

    def test_to_middle_stage(self):
        result = _validate_stage_range(to_stage="parse")
        assert result == ("ingest", "decrypt", "parse")

    def test_to_first_stage(self):
        result = _validate_stage_range(to_stage="ingest")
        assert result == ("ingest",)

    def test_from_and_to_range(self):
        result = _validate_stage_range(from_stage="decrypt", to_stage="classify")
        assert result == ("decrypt", "parse", "classify")

    def test_single_stage(self):
        result = _validate_stage_range(from_stage="parse", to_stage="parse")
        assert result == ("parse",)

    def test_invalid_from_stage(self):
        with pytest.raises(ValueError, match="無效的階段名稱.*'invalid'"):
            _validate_stage_range(from_stage="invalid")

    def test_invalid_to_stage(self):
        with pytest.raises(ValueError, match="無效的階段名稱.*'unknown'"):
            _validate_stage_range(to_stage="unknown")

    def test_reversed_order_raises(self):
        with pytest.raises(ValueError, match="必須在.*之前或相同"):
            _validate_stage_range(from_stage="classify", to_stage="decrypt")

    def test_adjacent_stages(self):
        result = _validate_stage_range(from_stage="parse", to_stage="classify")
        assert result == ("parse", "classify")

    @pytest.mark.parametrize("stage", STAGE_ORDER)
    def test_each_stage_valid_as_from(self, stage):
        result = _validate_stage_range(from_stage=stage)
        assert stage in result
        assert result[0] == stage

    @pytest.mark.parametrize("stage", STAGE_ORDER)
    def test_each_stage_valid_as_to(self, stage):
        result = _validate_stage_range(to_stage=stage)
        assert stage in result
        assert result[-1] == stage
