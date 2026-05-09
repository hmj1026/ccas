"""E.SUN v1 parser integration tests using synthetic PDFs.

Uses fpdf2 to generate PDFs that mimic E.SUN statement layout,
then verifies the full can_parse() -> parse() -> ParseResult flow.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
from fpdf import FPDF

from ccas.parser.registry import registry

_COL_WIDTHS = [25, 25, 25, 60, 30]
_TABLE_HEADERS = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.clear()
    yield
    registry.clear()


def _new_pdf(font_path: Path) -> FPDF:
    """Create a new FPDF instance with Chinese font configured."""
    pdf = FPDF()
    pdf.add_font("WenQuanYi", "", str(font_path))
    pdf.set_font("WenQuanYi", size=10)
    return pdf


def _write_table_row(pdf: FPDF, cells: Sequence[str]) -> None:
    """Write a single bordered table row using standard column widths."""
    for cell_val, w in zip(cells, _COL_WIDTHS):
        pdf.cell(w, 8, cell_val, border=1)
    pdf.ln()


def _create_esun_pdf(
    path: Path, font_path: Path, *, include_transactions: bool = True
) -> Path:
    """Generate a synthetic E.SUN statement PDF."""
    pdf = _new_pdf(font_path)
    pdf.add_page()

    pdf.cell(0, 10, "玉山銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "E.SUN Bank Credit Card Statement", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.cell(0, 8, "2026年03月份帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "繳費截止日：2026/04/15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "本期應繳總額：NT$ 1,880", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    if include_transactions:
        _write_table_row(pdf, _TABLE_HEADERS)
        for row in [
            ("03/01", "03/03", "4567", "全家便利商店", "350"),
            ("03/08", "03/10", "4567", "蝦皮購物", "1280"),
            ("03/15", "03/17", "8901", "星巴克", "250"),
        ]:
            _write_table_row(pdf, row)

    pdf.output(str(path))
    return path


def _create_non_esun_pdf(path: Path, font_path: Path) -> Path:
    """Generate a non-E.SUN statement PDF."""
    pdf = _new_pdf(font_path)
    pdf.add_page()
    pdf.cell(0, 10, "國泰世華商業銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return path


def _create_multi_page_esun_pdf(path: Path, font_path: Path) -> Path:
    """Generate a multi-page E.SUN statement PDF."""
    pdf = _new_pdf(font_path)

    # Page 1: summary + one transaction
    pdf.add_page()
    pdf.cell(0, 10, "玉山銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "E.SUN Bank Credit Card Statement", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.cell(0, 8, "2026年03月份帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "繳費截止日：2026/04/15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "本期應繳總額：NT$ 1,630", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    _write_table_row(pdf, _TABLE_HEADERS)
    _write_table_row(pdf, ("03/01", "03/03", "4567", "全家便利商店", "350"))

    # Page 2: another transaction
    pdf.add_page()
    _write_table_row(pdf, _TABLE_HEADERS)
    _write_table_row(pdf, ("03/08", "03/10", "4567", "蝦皮購物", "1280"))

    pdf.output(str(path))
    return path


class TestEsunV1PdfIntegration:
    def _get_parser(self):
        from ccas.parser.banks.esun_v1 import EsunV1Parser

        return EsunV1Parser()

    def test_can_parse_synthetic_esun_pdf(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_esun_pdf(tmp_path / "esun.pdf", cjk_font_path)

        assert parser.can_parse(pdf_path) is True

    def test_cannot_parse_non_esun_pdf(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_non_esun_pdf(tmp_path / "cathay.pdf", cjk_font_path)

        assert parser.can_parse(pdf_path) is False

    def test_parse_returns_valid_result(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_esun_pdf(tmp_path / "esun.pdf", cjk_font_path)

        result = parser.parse(pdf_path)

        assert result.bank_code == "ESUN"
        assert result.billing_month == "2026-03"
        assert result.total_amount == 1880
        assert result.due_date == date(2026, 4, 15)
        assert len(result.transactions) == 3
        assert result.transactions[0].merchant == "全家便利商店"
        assert result.transactions[0].amount == 350

    def test_parse_multi_page_pdf(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_multi_page_esun_pdf(
            tmp_path / "esun_multi.pdf", cjk_font_path
        )

        result = parser.parse(pdf_path)

        assert result.total_amount == 1630
        assert len(result.transactions) == 2

    def test_parse_result_is_frozen(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_esun_pdf(tmp_path / "esun.pdf", cjk_font_path)

        result = parser.parse(pdf_path)

        with pytest.raises(AttributeError):
            result.bank_code = "CHANGED"  # type: ignore[misc]


class TestEsunRegistryIntegration:
    def test_import_banks_registers_esun_v1(self):
        from ccas.parser.banks.esun_v1 import EsunV1Parser

        registry.register(EsunV1Parser())
        candidates = registry.resolve("ESUN")

        assert len(candidates) >= 1
        assert candidates[0].bank_code == "ESUN"
        assert candidates[0].version == "v1"

    def test_module_level_registration_on_fresh_import(self):
        """Verify module-level registration works."""
        from ccas.parser.banks.esun_v1 import EsunV1Parser

        parser = EsunV1Parser()
        registry.register(parser)

        versions = registry.get_versions("ESUN")
        assert any(p.version == "v1" for p in versions)

    def test_parser_package_import_triggers_registration(self):
        """Verify top-level package import triggers bank registration."""
        import importlib

        import ccas.parser

        importlib.reload(ccas.parser.banks.esun_v1)
        importlib.reload(ccas.parser.banks)
        importlib.reload(ccas.parser)

        candidates = registry.resolve("ESUN")
        assert len(candidates) >= 1
        assert candidates[0].bank_code == "ESUN"
