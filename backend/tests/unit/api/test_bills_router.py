"""Bills router 單元測試。"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from ccas.api.routers.bills import _resolve_bill_pdf_path


class TestResolveBillPdfPath:
    def test_allows_file_within_staging_root(self, tmp_path: Path):
        allowed_root = tmp_path / "staging"
        bill_dir = allowed_root / "CTBC"
        bill_dir.mkdir(parents=True)
        pdf_path = bill_dir / "bill.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        result = _resolve_bill_pdf_path(str(pdf_path), str(allowed_root))

        assert result == pdf_path.resolve()

    def test_file_outside_staging_root_rebases_to_404(self, tmp_path: Path):
        """路徑不在 staging root 下時，rebase 後檔案不存在應回傳 404。"""
        allowed_root = tmp_path / "staging"
        allowed_root.mkdir()
        outside_pdf = tmp_path / "outside.pdf"
        outside_pdf.write_bytes(b"%PDF-1.4 test")

        with pytest.raises(HTTPException) as exc_info:
            _resolve_bill_pdf_path(str(outside_pdf), str(allowed_root))
        assert exc_info.value.status_code == 404

    def test_rebases_path_from_different_environment(self, tmp_path: Path):
        """Docker 環境下，以本機路徑儲存的 file_path 應自動 rebase 到目前 staging_dir。"""
        docker_staging = tmp_path / "data" / "staging"
        bill_dir = docker_staging / "CTBC"
        bill_dir.mkdir(parents=True)
        pdf = bill_dir / "abc123_bill.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")

        # Simulate a path stored when running locally under a different root
        local_path = "/Users/paul/Project/ccas/backend/data/staging/CTBC/abc123_bill.pdf"

        result = _resolve_bill_pdf_path(local_path, str(docker_staging))

        assert result == pdf.resolve()

    def test_rebase_rejects_when_rebased_file_missing(self, tmp_path: Path):
        """Rebase 後檔案不存在時應回傳 404。"""
        docker_staging = tmp_path / "data" / "staging"
        docker_staging.mkdir(parents=True)

        local_path = "/Users/paul/Project/ccas/backend/data/staging/CTBC/missing.pdf"

        with pytest.raises(HTTPException) as exc_info:
            _resolve_bill_pdf_path(local_path, str(docker_staging))
        assert exc_info.value.status_code == 404
