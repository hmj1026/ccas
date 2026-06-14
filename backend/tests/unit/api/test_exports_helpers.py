"""Unit tests for ``ccas.api.routers.exports`` pure helpers.

涵蓋 ``_build_query`` 與 ``_row_values``；不依賴 DB session（compile
SQL 字面值即可驗 filter 是否組對；row_values 接 Transaction instance
直接呼叫即可）。
"""

from __future__ import annotations

import json
from datetime import date

from ccas.api.routers.exports import _build_query, _neutralize, _row_values
from ccas.storage.models import Transaction


def _compile(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestBuildQuery:
    def test_no_filters_just_join_and_order(self):
        sql = _compile(_build_query(start=None, end=None, bank=None, category=None))
        assert "JOIN" in sql.upper()
        assert "ORDER BY" in sql.upper()
        assert "WHERE" not in sql.upper()

    def test_start_and_end_apply_date_window(self):
        sql = _compile(
            _build_query(
                start=date(2026, 1, 1),
                end=date(2026, 12, 31),
                bank=None,
                category=None,
            )
        )
        assert "2026-01-01" in sql
        assert "2026-12-31" in sql

    def test_bank_filter(self):
        sql = _compile(_build_query(start=None, end=None, bank="CTBC", category=None))
        assert "'CTBC'" in sql

    def test_category_filter(self):
        sql = _compile(_build_query(start=None, end=None, bank=None, category="餐飲"))
        assert "'餐飲'" in sql


class TestRowValues:
    def test_minimal_row_no_user_fields(self):
        txn = Transaction(
            bill_id=1,
            trans_date=date(2026, 5, 10),
            posting_date=None,
            merchant="星巴克",
            amount=150,
            currency="TWD",
            original_amount=None,
            card_last4=None,
            category=None,
        )
        row = _row_values(txn, "CTBC", "2026-05", include_user_fields=False)
        # base has 10 columns; no user fields
        assert len(row) == 10
        assert row[0] == "2026-05-10"
        assert row[1] == ""  # posting_date None
        assert row[2] == "CTBC"
        assert row[3] == "2026-05"
        assert row[4] == "星巴克"
        assert row[5] == 150
        assert row[6] == "TWD"
        assert row[7] == ""  # original_amount None
        assert row[8] == ""  # card_last4 None
        assert row[9] == ""  # category None

    def test_full_row_with_user_fields_serializes_tags_as_json(self):
        txn = Transaction(
            bill_id=1,
            trans_date=date(2026, 5, 10),
            posting_date=date(2026, 5, 12),
            merchant="UBER",
            amount=300,
            currency="TWD",
            original_amount=10,
            card_last4="1234",
            category="交通",
            manual_category_override=True,
            tags=["保留", "公務"],
            merchant_alias="Uber Taxi",
            note="出差",
        )
        row = _row_values(txn, "ESUN", "2026-05", include_user_fields=True)
        assert len(row) == 14
        assert row[1] == "2026-05-12"
        assert row[7] == 10
        assert row[8] == "1234"
        assert row[10] == "true"
        assert json.loads(row[11]) == ["保留", "公務"]
        assert row[12] == "Uber Taxi"
        assert row[13] == "出差"

    def test_user_fields_default_when_unset(self):
        txn = Transaction(
            bill_id=1,
            trans_date=date(2026, 5, 10),
            merchant="X",
            amount=1,
            currency="TWD",
        )
        row = _row_values(txn, "CTBC", "2026-05", include_user_fields=True)
        # manual_category_override defaults to False at ORM level
        assert row[10] == "false"
        # tags default → json '[]'
        assert json.loads(row[11]) == []
        assert row[12] == ""
        assert row[13] == ""


class TestFormulaInjectionNeutralization:
    """OWASP CSV Formula Injection 防護（R03）。"""

    def test_neutralize_prefixes_formula_leading_strings(self):
        assert _neutralize("=HYPERLINK(1)") == "'=HYPERLINK(1)"
        assert _neutralize("+1+2") == "'+1+2"
        assert _neutralize("-2+3") == "'-2+3"
        assert _neutralize("@SUM(A1)") == "'@SUM(A1)"
        assert _neutralize("\tcmd") == "'\tcmd"
        assert _neutralize("\rcmd") == "'\rcmd"

    def test_neutralize_passes_safe_values_through(self):
        assert _neutralize("星巴克") == "星巴克"
        assert _neutralize("") == ""
        assert _neutralize(150) == 150  # numeric untouched
        assert _neutralize(None) is None

    def test_row_values_neutralizes_user_controlled_fields(self):
        txn = Transaction(
            bill_id=1,
            trans_date=date(2026, 5, 10),
            merchant="=cmd|'/C calc'!A1",
            amount=100,
            currency="TWD",
            merchant_alias="+attack",
            note="@evil()",
            tags=["x"],
        )
        row = _row_values(txn, "CTBC", "2026-05", include_user_fields=True)
        assert row[4] == "'=cmd|'/C calc'!A1"  # merchant neutralized
        assert row[5] == 100  # numeric amount unchanged
        assert row[12] == "'+attack"  # merchant_alias neutralized
        assert row[13] == "'@evil()"  # note neutralized
