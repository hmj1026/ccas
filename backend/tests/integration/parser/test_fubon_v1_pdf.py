"""Fubon v1 parser integration tests using synthetic PDFs.

Uses fpdf2 to generate PDFs that mimic Taipei Fubon Bank statement layout,
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


def _create_fubon_pdf(
    path: Path, font_path: Path, *, include_transactions: bool = True
) -> Path:
    """Generate a synthetic Taipei Fubon Bank statement PDF."""
    pdf = _new_pdf(font_path)
    pdf.add_page()

    pdf.cell(0, 10, "台北富邦銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        8,
        "Taipei Fubon Bank Credit Card Statement",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(5)
    pdf.cell(0, 8, "帳單月份：2026年03月", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "繳費截止日：2026/04/15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "本期應繳總額：NT$ 15,800", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    if include_transactions:
        _write_table_row(pdf, _TABLE_HEADERS)
        for row in [
            ("03/05", "03/07", "8899", "全聯福利中心", "680"),
            ("03/10", "03/12", "8899", "台灣大哥大", "499"),
            ("03/15", "03/17", "8899", "誠品書店", "1,250"),
        ]:
            _write_table_row(pdf, row)

    pdf.output(str(path))
    return path


def _create_non_fubon_pdf(path: Path, font_path: Path) -> Path:
    """Generate a non-Fubon statement PDF."""
    pdf = _new_pdf(font_path)
    pdf.add_page()
    pdf.cell(0, 10, "中國信託商業銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return path


def _create_multi_page_fubon_pdf(path: Path, font_path: Path) -> Path:
    """Generate a multi-page Fubon statement PDF."""
    pdf = _new_pdf(font_path)

    # Page 1: summary + one transaction
    pdf.add_page()
    pdf.cell(0, 10, "台北富邦銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        8,
        "Taipei Fubon Bank Credit Card Statement",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(5)
    pdf.cell(0, 8, "帳單月份：2026年03月", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "繳費截止日：2026/04/15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "本期應繳總額：NT$ 1,179", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    _write_table_row(pdf, _TABLE_HEADERS)
    _write_table_row(pdf, ("03/05", "03/07", "8899", "全聯福利中心", "680"))

    # Page 2: another transaction
    pdf.add_page()
    _write_table_row(pdf, _TABLE_HEADERS)
    _write_table_row(pdf, ("03/10", "03/12", "8899", "台灣大哥大", "499"))

    pdf.output(str(path))
    return path


class TestFubonV1PdfIntegration:
    def _get_parser(self):
        from ccas.parser.banks.fubon_v1 import FubonV1Parser

        return FubonV1Parser()

    def test_can_parse_fubon_pdf(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_fubon_pdf(tmp_path / "fubon.pdf", cjk_font_path)

        assert parser.can_parse(pdf_path) is True

    def test_cannot_parse_non_fubon_pdf(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_non_fubon_pdf(tmp_path / "ctbc.pdf", cjk_font_path)

        assert parser.can_parse(pdf_path) is False

    def test_parse_returns_valid_result(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_fubon_pdf(tmp_path / "fubon.pdf", cjk_font_path)

        result = parser.parse(pdf_path)

        assert result.bank_code == "FUBON"
        assert result.billing_month == "2026-03"
        assert result.total_amount == 15800
        assert result.due_date == date(2026, 4, 15)
        assert len(result.transactions) == 3
        assert result.transactions[0].merchant == "全聯福利中心"
        assert result.transactions[0].amount == 680

    def test_parse_multi_page_pdf(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_multi_page_fubon_pdf(
            tmp_path / "fubon_multi.pdf", cjk_font_path
        )

        result = parser.parse(pdf_path)

        assert result.total_amount == 1179
        assert len(result.transactions) == 2

    def test_parse_result_is_frozen(self, tmp_path, cjk_font_path):
        parser = self._get_parser()
        pdf_path = _create_fubon_pdf(tmp_path / "fubon.pdf", cjk_font_path)

        result = parser.parse(pdf_path)

        with pytest.raises(AttributeError):
            result.bank_code = "CHANGED"  # type: ignore[misc]


class TestFubonRegistryIntegration:
    def test_import_banks_registers_fubon_v1(self):
        from ccas.parser.banks.fubon_v1 import FubonV1Parser

        registry.register(FubonV1Parser())
        candidates = registry.resolve("FUBON")

        assert len(candidates) >= 1
        assert candidates[0].bank_code == "FUBON"
        assert candidates[0].version == "v1"

    def test_module_level_registration_on_fresh_import(self):
        """Verify module-level registration works."""
        from ccas.parser.banks.fubon_v1 import FubonV1Parser

        parser = FubonV1Parser()
        registry.register(parser)

        versions = registry.get_versions("FUBON")
        assert any(p.version == "v1" for p in versions)

    def test_parser_package_import_triggers_registration(self):
        """Production code imports ccas.parser, not ccas.parser.banks.

        Verify the top-level package import triggers bank registration.
        """
        import importlib

        import ccas.parser

        importlib.reload(ccas.parser.banks.fubon_v1)
        importlib.reload(ccas.parser.banks)
        importlib.reload(ccas.parser)

        candidates = registry.resolve("FUBON")
        assert len(candidates) >= 1
        assert candidates[0].bank_code == "FUBON"
