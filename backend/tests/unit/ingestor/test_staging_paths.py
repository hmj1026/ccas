"""Unit tests for staging path storage/resolution helpers."""

from pathlib import Path

import pytest

from ccas.ingestor.staging import (
    build_staged_path,
    resolve_staged_path,
    staged_path_for_storage,
)


class TestStagedPathForStorage:
    def test_converts_absolute_to_relative(self, tmp_path: Path):
        staging_dir = str(tmp_path / "staging")
        abs_path = tmp_path / "staging" / "FUBON" / "abc_test.pdf"
        result = staged_path_for_storage(staging_dir, abs_path)
        assert result == "FUBON/abc_test.pdf"

    def test_roundtrip_with_build(self, tmp_path: Path):
        staging_dir = str(tmp_path / "staging")
        abs_path = build_staged_path(staging_dir, "FUBON", "msg123456789", "bill.pdf")
        relative = staged_path_for_storage(staging_dir, abs_path)
        assert not Path(relative).is_absolute()
        resolved = resolve_staged_path(staging_dir, relative)
        assert resolved == abs_path


class TestResolveStagedPath:
    def test_resolves_relative_path(self):
        result = resolve_staged_path("/data/staging", "FUBON/abc.pdf")
        assert result == Path("/data/staging/FUBON/abc.pdf")

    def test_legacy_absolute_remapped_to_staging_root(self):
        result = resolve_staged_path("/data/staging", "/old/path/FUBON/abc.pdf")
        assert result == Path("/data/staging/FUBON/abc.pdf")

    def test_legacy_absolute_same_root_preserved(self):
        result = resolve_staged_path("/data/staging", "/data/staging/FUBON/abc.pdf")
        assert result == Path("/data/staging/FUBON/abc.pdf")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError):
            resolve_staged_path("/data/staging", "../../etc/passwd")

    def test_absolute_path_remapped_into_staging(self):
        result = resolve_staged_path("/data/staging", "/etc/passwd")
        assert result == Path("/data/staging/etc/passwd")

    def test_rejects_legacy_absolute_with_dotdot_tail(self):
        with pytest.raises(ValueError, match="traversal"):
            resolve_staged_path("/data/staging", "/a/b/c/..")

    def test_local_staging_dir(self):
        result = resolve_staged_path("./data/staging", "FUBON/abc.pdf")
        assert "FUBON/abc.pdf" in str(result)

    def test_docker_staging_dir(self):
        result = resolve_staged_path("/data/staging", "FUBON/abc.pdf")
        assert result == Path("/data/staging/FUBON/abc.pdf")
