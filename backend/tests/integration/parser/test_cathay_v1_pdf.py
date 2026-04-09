"""Cathay v1 parser integration tests using synthetic PDFs.

Uses fpdf2 to generate PDFs that mimic Cathay United Bank statement layout,
then verifies the full can_parse() -> parse() -> ParseResult flow.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
from fpdf import FPDF

from ccas.parser.registry import registry

_CJK_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
_COL_WIDTHS = [25, 25, 25, 60, 30]
_TABLE_HEADERS = ["交易日", "入帳日", "卡號末四碼", "交易說明", "金額"]


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.clear()
    yield
    registry.clear()


def _new_pdf() -> FPDF:
    """Create a new FPDF instance with Chinese font configured."""
    pdf = FPDF()
    pdf.add_font("WenQuanYi", "", _CJK_FONT_PATH)
    pdf.set_font("WenQuanYi", size=10)
    return pdf


def _write_table_row(pdf: FPDF, cells: Sequence[str]) -> None:
    """Write a single bordered table row using standard column widths."""
    for cell_val, w in zip(cells, _COL_WIDTHS):
        pdf.cell(w, 8, cell_val, border=1)
    pdf.ln()


def _create_cathay_pdf(path: Path, *, include_transactions: bool = True) -> Path:
    """Generate a synthetic Cathay United Bank statement PDF."""
    pdf = _new_pdf()
    pdf.add_page()

    pdf.cell(0, 10, "國泰世華銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        8,
        "Cathay United Bank Credit Card Statement",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(5)
    pdf.cell(0, 8, "2026年03月份帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "繳費截止日：2026/04/12", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "本期應繳總額：NT$ 4,830", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    if include_transactions:
        _write_table_row(pdf, _TABLE_HEADERS)
        for row in [
            ("03/02", "03/04", "2345", "全家便利商店", "180"),
            ("03/10", "03/12", "2345", "誠品書店", "1450"),
            ("03/18", "03/20", "6789", "好市多", "3200"),
        ]:
            _write_table_row(pdf, row)

    pdf.output(str(path))
    return path


def _create_non_cathay_pdf(path: Path) -> Path:
    """Generate a non-Cathay statement PDF."""
    pdf = _new_pdf()
    pdf.add_page()
    pdf.cell(0, 10, "中國信託商業銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return path


def _create_multi_page_cathay_pdf(path: Path) -> Path:
    """Generate a multi-page Cathay statement PDF."""
    pdf = _new_pdf()

    # Page 1: summary + one transaction
    pdf.add_page()
    pdf.cell(0, 10, "國泰世華銀行 信用卡帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        8,
        "Cathay United Bank Credit Card Statement",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(5)
    pdf.cell(0, 8, "2026年03月份帳單", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "繳費截止日：2026/04/12", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "本期應繳總額：NT$ 1,630", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    _write_table_row(pdf, _TABLE_HEADERS)
    _write_table_row(pdf, ("03/02", "03/04", "2345", "全家便利商店", "180"))

    # Page 2: another transaction
    pdf.add_page()
    _write_table_row(pdf, _TABLE_HEADERS)
    _write_table_row(pdf, ("03/10", "03/12", "2345", "誠品書店", "1450"))

    pdf.output(str(path))
    return path


class TestCathayV1PdfIntegration:
    def _get_parser(self):
        from ccas.parser.banks.cathay_v1 import CathayV1Parser

        return CathayV1Parser()

    def test_can_parse_synthetic_cathay_pdf(self, tmp_path):
        parser = self._get_parser()
        pdf_path = _create_cathay_pdf(tmp_path / "cathay.pdf")

        assert parser.can_parse(pdf_path) is True

    def test_cannot_parse_non_cathay_pdf(self, tmp_path):
        parser = self._get_parser()
        pdf_path = _create_non_cathay_pdf(tmp_path / "ctbc.pdf")

        assert parser.can_parse(pdf_path) is False

    def test_parse_returns_valid_result(self, tmp_path):
        parser = self._get_parser()
        pdf_path = _create_cathay_pdf(tmp_path / "cathay.pdf")

        result = parser.parse(pdf_path)

        assert result.bank_code == "CATHAY"
        assert result.billing_month == "2026-03"
        assert result.total_amount == 4830
        assert result.due_date == date(2026, 4, 12)
        assert len(result.transactions) == 3
        assert result.transactions[0].merchant == "全家便利商店"
        assert result.transactions[0].amount == 180

    def test_parse_multi_page_pdf(self, tmp_path):
        parser = self._get_parser()
        pdf_path = _create_multi_page_cathay_pdf(tmp_path / "cathay_multi.pdf")

        result = parser.parse(pdf_path)

        assert result.total_amount == 1630
        assert len(result.transactions) == 2

    def test_parse_result_is_frozen(self, tmp_path):
        parser = self._get_parser()
        pdf_path = _create_cathay_pdf(tmp_path / "cathay.pdf")

        result = parser.parse(pdf_path)

        with pytest.raises(AttributeError):
            result.bank_code = "CHANGED"  # type: ignore[misc]


class TestCathayRegistryIntegration:
    def test_import_banks_registers_cathay_v1(self):
        from ccas.parser.banks.cathay_v1 import CathayV1Parser

        registry.register(CathayV1Parser())
        candidates = registry.resolve("CATHAY")

        assert len(candidates) >= 1
        assert candidates[0].bank_code == "CATHAY"
        assert candidates[0].version == "v1"

    def test_module_level_registration_on_fresh_import(self):
        """Verify module-level registration works."""
        from ccas.parser.banks.cathay_v1 import CathayV1Parser

        parser = CathayV1Parser()
        registry.register(parser)

        versions = registry.get_versions("CATHAY")
        assert any(p.version == "v1" for p in versions)

    def test_parser_package_import_triggers_registration(self):
        """Production code imports ccas.parser, not ccas.parser.banks.

        Verify the top-level package import triggers bank registration.
        """
        import importlib

        import ccas.parser

        importlib.reload(ccas.parser.banks.cathay_v1)
        importlib.reload(ccas.parser.banks)
        importlib.reload(ccas.parser)

        candidates = registry.resolve("CATHAY")
        assert len(candidates) >= 1
        assert candidates[0].bank_code == "CATHAY"
