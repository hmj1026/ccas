"""API Literal 與 storage StrEnum 的 SSOT 同步測試。

pyright 不接受動態建構的 ``Literal``，因此 ``ccas.api.schemas`` 保留
顯式 Literal 宣告；本測試保證每個 Literal 的值集合與對應 StrEnum
（SSOT，定義於 ``ccas.storage.models``）完全一致，防止再度漂移
（如 decrypt_failed / manual_review_needed 曾缺漏於 API contract）。
"""

from enum import StrEnum
from typing import get_args

import pytest

from ccas.api import schemas
from ccas.storage import models

LITERAL_ENUM_PAIRS: list[tuple[str, object, type[StrEnum]]] = [
    (
        "StagedAttachmentStatusLiteral",
        schemas.StagedAttachmentStatusLiteral,
        models.StagedAttachmentStatus,
    ),
    (
        "PipelineRunStatusLiteral",
        schemas.PipelineRunStatusLiteral,
        models.PipelineRunStatus,
    ),
    ("PatternTypeLiteral", schemas.PatternTypeLiteral, models.PatternType),
    ("ReminderChannelLiteral", schemas.ReminderChannelLiteral, models.ReminderChannel),
    ("BudgetScopeLiteral", schemas.BudgetScopeLiteral, models.BudgetScope),
]


@pytest.mark.parametrize(
    ("name", "literal", "enum_cls"),
    LITERAL_ENUM_PAIRS,
    ids=[name for name, _, _ in LITERAL_ENUM_PAIRS],
)
async def test_literal_values_match_strenum(
    name: str, literal: object, enum_cls: type[StrEnum]
):
    literal_values = get_args(literal)
    enum_values = [member.value for member in enum_cls]
    assert len(literal_values) == len(set(literal_values)), (
        f"{name} contains duplicate values"
    )
    assert set(literal_values) == set(enum_values), (
        f"{name} out of sync with {enum_cls.__name__}: "
        f"literal-only={set(literal_values) - set(enum_values)}, "
        f"enum-only={set(enum_values) - set(literal_values)}"
    )


async def test_staged_attachment_status_has_all_nine_values():
    assert {member.value for member in models.StagedAttachmentStatus} == {
        "staged",
        "decrypted",
        "decrypt_failed",
        "parsed",
        "parse_skipped",
        "parse_failed",
        "manual_review_needed",
        "failed",
        "fetch_expired",
    }
