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

    def test_rejects_file_outside_staging_root(self, tmp_path: Path):
        allowed_root = tmp_path / "staging"
        allowed_root.mkdir()
        pdf_path = tmp_path / "outside.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        with pytest.raises(HTTPException, match="允許範圍"):
            _resolve_bill_pdf_path(str(pdf_path), str(allowed_root))
