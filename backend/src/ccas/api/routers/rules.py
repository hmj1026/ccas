"""User classification rules API（bills-management-and-insights §4）。

CRUD endpoints for ``classification_rules`` 表，加上即時規則測試端點供 UI 預覽：

- ``GET /api/rules``：列表（priority DESC、id ASC），可選 ``?enabled=`` filter
- ``POST /api/rules``：新增規則
- ``PUT /api/rules/{id}``：更新（部分欄位）
- ``DELETE /api/rules/{id}``：刪除
- ``POST /api/rules/test``：即時 sample_text 比對預覽（不寫 DB）

所有端點都套上 ``verify_token`` dependency（透過 router 全域 dependency）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    ClassificationRuleCreateRequest,
    ClassificationRuleItem,
    ClassificationRuleTestRequest,
    ClassificationRuleTestResponse,
    ClassificationRuleUpdateRequest,
)
from ccas.classifier.user_rules import UserRule, UserRuleMatcher
from ccas.storage.database import get_db_session
from ccas.storage.models import (
    Category,
    PatternType,
    UserClassificationRule,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _integrity_error_to_http(exc: IntegrityError) -> HTTPException:
    """Map a DB IntegrityError to a friendly 422 without leaking schema.

    ``str(exc.orig)`` exposes table/column names to the client (e.g.
    ``UNIQUE constraint failed: classification_rules.pattern``). We log the
    original error server-side for diagnosis and return a sanitized
    Traditional-Chinese message keyed off the constraint class.
    """
    raw = str(exc.orig)
    logger.warning("Rules IntegrityError: %s", raw)
    if "UNIQUE" in raw:
        detail = "相同 pattern 的規則已存在"
    elif "FOREIGN KEY" in raw:
        detail = "指定的 category_id 不存在"
    else:
        detail = "資料完整性錯誤，請確認輸入值"
    return HTTPException(status_code=422, detail=detail)


def _to_item(
    rule: UserClassificationRule, category_name: str
) -> ClassificationRuleItem:
    # SQLAlchemy String column 讀回為 str；新建立時是 PatternType enum。
    # 兩者皆轉成字串字面值（"keyword" / "exact" / "regex"）。
    pattern_type_str = (
        rule.pattern_type.value
        if isinstance(rule.pattern_type, PatternType)
        else rule.pattern_type
    )
    return ClassificationRuleItem(
        id=rule.id,
        pattern=rule.pattern,
        pattern_type=pattern_type_str,  # type: ignore[arg-type]
        category_id=rule.category_id,
        category_name=category_name,
        priority=rule.priority,
        enabled=rule.enabled,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _resolve_category_name(session: AsyncSession, category_id: int) -> str:
    """Lookup ``categories.category`` 字串值；不存在拋 422。"""
    cat = await session.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=422, detail=f"category_id={category_id} 不存在")
    return cat.category


@router.get("", response_model=ApiResponse[list[ClassificationRuleItem]])
async def list_rules(
    enabled: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ClassificationRuleItem]]:
    """列出全部使用者規則（priority DESC、id ASC），可選 enabled filter。"""
    stmt = (
        select(UserClassificationRule, Category.category)
        .join(Category, UserClassificationRule.category_id == Category.id)
        .order_by(
            UserClassificationRule.priority.desc(),
            UserClassificationRule.id.asc(),
        )
    )
    if enabled is not None:
        stmt = stmt.where(UserClassificationRule.enabled.is_(enabled))
    result = await session.execute(stmt)
    items = [_to_item(r, name) for r, name in result.all()]
    return ApiResponse(data=items)


@router.post(
    "",
    response_model=ApiResponse[ClassificationRuleItem],
    status_code=201,
)
async def create_rule(
    body: ClassificationRuleCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ClassificationRuleItem]:
    """新增規則；FK violation → 422。"""
    category_name = await _resolve_category_name(session, body.category_id)

    rule = UserClassificationRule(
        pattern=body.pattern,
        pattern_type=PatternType(body.pattern_type),
        category_id=body.category_id,
        priority=body.priority,
        enabled=body.enabled,
    )
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _integrity_error_to_http(exc) from exc
    await session.refresh(rule)
    return ApiResponse(data=_to_item(rule, category_name))


@router.put("/{rule_id}", response_model=ApiResponse[ClassificationRuleItem])
async def update_rule(
    rule_id: int,
    body: ClassificationRuleUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ClassificationRuleItem]:
    """更新規則；不存在 → 404；FK violation → 422。"""
    rule = await session.get(UserClassificationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"rule_id={rule_id} 不存在")

    if body.pattern is not None:
        rule.pattern = body.pattern
    if body.pattern_type is not None:
        rule.pattern_type = PatternType(body.pattern_type)
    if body.category_id is not None:
        await _resolve_category_name(session, body.category_id)
        rule.category_id = body.category_id
    if body.priority is not None:
        rule.priority = body.priority
    if body.enabled is not None:
        rule.enabled = body.enabled

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _integrity_error_to_http(exc) from exc
    await session.refresh(rule)
    category_name = await _resolve_category_name(session, rule.category_id)
    return ApiResponse(data=_to_item(rule, category_name))


@router.delete("/{rule_id}", response_model=ApiResponse[dict[str, int]])
async def delete_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, int]]:
    """刪除規則；不存在 → 404。"""
    rule = await session.get(UserClassificationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"rule_id={rule_id} 不存在")
    await session.delete(rule)
    await session.commit()
    return ApiResponse(data={"deleted_id": rule_id})


@router.post(
    "/test",
    response_model=ApiResponse[ClassificationRuleTestResponse],
)
async def test_rule(
    body: ClassificationRuleTestRequest,
) -> ApiResponse[ClassificationRuleTestResponse]:
    """以給定 pattern + pattern_type 測試 sample_text 是否命中（不寫 DB）。

    重用 ``UserRuleMatcher`` 的同步 match 邏輯（fail-soft），確保預覽結果與 pipeline
    classify 一致。此端點直接建構 matcher、不經 ``load()`` 期 burn-in；ReDoS 防護改由
    request schema 把關（``schemas._NESTED_QUANTIFIER_RE`` 拒收危險 pattern、並對
    pattern / sample_text 設長度上限）。
    """
    probe = UserRule(
        id=0,
        pattern=body.pattern,
        pattern_type=PatternType(body.pattern_type),
        category_name="__probe__",
        priority=0,
    )
    matcher = UserRuleMatcher([probe])
    matched = await matcher.match(body.sample_text)
    return ApiResponse(data=ClassificationRuleTestResponse(matches=matched is not None))
