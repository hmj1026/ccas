"""Unit tests for ccas.storage.paths path-traversal protection.

These mirror the guarantees previously asserted against
``ccas.ingestor.staging`` (now re-exported) but pin them directly to the
relocated ``ccas.storage.paths`` module so the traversal guard cannot silently
regress after the move.
"""

from pathlib import Path

import pytest

from ccas.storage.paths import (
    build_staged_path,
    resolve_staged_path,
    staged_path_for_storage,
)


class TestBuildStagedPathTraversalGuard:
    def test_strips_filename_path_segments(self):
        """檔名含 ../ 片段時只保留 basename，不逃逸 bank 目錄。"""
        result = build_staged_path(
            "/data/staging", "CTBC", "abc123def456xyz", "../../evil.pdf"
        )
        assert result == Path("/data/staging/CTBC/abc123def456_evil.pdf")

    def test_rejects_empty_or_dotdot_filename(self):
        with pytest.raises(ValueError, match="filename"):
            build_staged_path("/data/staging", "CTBC", "abc123", "../")

    def test_rejects_malicious_bank_code(self):
        """bank_code 含路徑控制字元應直接拒絕（不可用於目錄逃逸）。"""
        with pytest.raises(ValueError, match="bank_code"):
            build_staged_path("/data/staging", "../etc", "abc123", "bill.pdf")

    def test_rejects_bank_code_with_slash(self):
        with pytest.raises(ValueError, match="bank_code"):
            build_staged_path("/data/staging", "a/b", "abc123", "bill.pdf")


class TestResolveStagedPathTraversalGuard:
    def test_resolves_plain_relative(self):
        result = resolve_staged_path("/data/staging", "FUBON/abc.pdf")
        assert result == Path("/data/staging/FUBON/abc.pdf")

    def test_rejects_relative_traversal(self):
        with pytest.raises(ValueError):
            resolve_staged_path("/data/staging", "../../etc/passwd")

    def test_rejects_legacy_absolute_with_dotdot_tail(self):
        with pytest.raises(ValueError, match="traversal"):
            resolve_staged_path("/data/staging", "/a/b/c/..")

    def test_legacy_absolute_remapped_into_staging_root(self):
        result = resolve_staged_path("/data/staging", "/old/path/FUBON/abc.pdf")
        assert result == Path("/data/staging/FUBON/abc.pdf")


class TestStagedPathForStorageRoundtrip:
    def test_roundtrip(self, tmp_path: Path):
        staging_dir = str(tmp_path / "staging")
        abs_path = build_staged_path(staging_dir, "FUBON", "msg123456789", "bill.pdf")
        relative = staged_path_for_storage(staging_dir, abs_path)
        assert not Path(relative).is_absolute()
        assert resolve_staged_path(staging_dir, relative) == abs_path
