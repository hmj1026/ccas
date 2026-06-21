"""Budget evaluator (bills-management-and-insights §6.6-§6.10).

每日由 scheduler 觸發 ``evaluate_budgets``：

1. 遍歷 ``budgets`` 表所有 enabled rows
2. 對每個 budget，依 scope 累計當月花費（與 router ``current-period`` 相同邏輯）
3. 若百分比 ≥ ``alert_threshold_percent`` 且更高 threshold 尚未觸發，
   寫入 ``budget_alerts`` row + 加入待推訊息 buffer
4. 觸發 100% 也視為更高 threshold（即 80% 已通知後再越 100% 仍會推一次）
5. Telegram 訊息聚合：所有當次新增 alerts 合併為單則訊息再 ``send_message``

去重邏輯：以 ``(budget_id, period_year_month, threshold_breached_percent)``
查詢 ``budget_alerts``；存在則跳過。實際 threshold ladder 為
``[alert_threshold_percent, 100]``（兩階段）。

Telegram 未設定 / 推送失敗：log warning，不 raise；alerts 仍寫入 DB
（保留 banner / 後續手動補推可能性）。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.messaging import send_message
from ccas.storage.models import (
    Budget,
    BudgetAlert,
    BudgetScope,
)
from ccas.storage.queries import aggregate_current_periods

logger = logging.getLogger(__name__)


def _current_year_month(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _scope_label(b: Budget) -> str:
    if b.scope == BudgetScope.MONTHLY_TOTAL:
        return "整月支出"
    if b.scope == BudgetScope.MONTHLY_CATEGORY:
        return f"類別「{b.scope_ref}」"
    if b.scope == BudgetScope.MONTHLY_BANK:
        return f"銀行「{b.scope_ref}」"
    return str(b.scope)


def _format_aggregated_message(
    period: str, alerts: list[tuple[Budget, BudgetAlert]]
) -> str:
    """聚合多筆 alert 為單則 Telegram 訊息。"""
    lines = [f"預算超支警示（{period}）", ""]
    for budget, alert in alerts:
        pct = alert.threshold_breached_percent
        cur = alert.current_amount_ntd
        amt = budget.amount_ntd
        lines.append(f"- {_scope_label(budget)}：${cur:,} / ${amt:,}（{pct}% 已達）")
    return "\n".join(lines)


async def _existing_alerts_map(
    session: AsyncSession, budget_ids: list[int], period_ym: str
) -> dict[tuple[int, int], BudgetAlert]:
    """一次查出多個 budget 在當期既有的 alert rows，避免迴圈內 N+1。

    回傳 ``{(budget_id, threshold_breached_percent): BudgetAlert}``。同時涵蓋
    notified=True（已完成）與 notified=False（已建立但推播未成功，待補推）兩
    種狀態，由呼叫端依 ``notified`` 判定是否略過或重用。
    """
    result: dict[tuple[int, int], BudgetAlert] = {}
    if not budget_ids:
        return result
    stmt = select(BudgetAlert).where(
        BudgetAlert.budget_id.in_(budget_ids),
        BudgetAlert.period_year_month == period_ym,
    )
    for alert in (await session.execute(stmt)).scalars().all():
        result[(alert.budget_id, alert.threshold_breached_percent)] = alert
    return result


async def evaluate_budgets(
    session: AsyncSession,
    *,
    today: date | None = None,
) -> dict[str, int]:
    """Evaluate all enabled budgets for the current period.

    Returns:
        ``{"alerts_triggered": N, "skipped": M}``
    """
    period = _current_year_month(today)
    enabled_stmt = select(Budget).where(Budget.enabled.is_(True))
    budgets = (await session.execute(enabled_stmt)).scalars().all()

    triggered: list[tuple[Budget, BudgetAlert]] = []
    skipped = 0

    # 一次撈出所有 enabled budget 在當期的既有 alert thresholds + 當月累計花費，
    # 兩者皆批次查詢（R28 + R-budget-N+1：消除迴圈內 N+1）。
    active_budgets = [b for b in budgets if b.amount_ntd > 0]
    active_ids = [b.id for b in active_budgets]
    existing_map = await _existing_alerts_map(session, active_ids, period)
    current_map = await aggregate_current_periods(session, active_budgets, period)

    for budget in budgets:
        if budget.amount_ntd <= 0:
            skipped += 1
            continue

        current = current_map.get(budget.id, 0)

        # Two-tier ladder: configured threshold + 100% (over-budget)
        thresholds: list[int] = sorted({budget.alert_threshold_percent, 100})
        for tier in thresholds:
            existing_alert = existing_map.get((budget.id, tier))
            # 已完成（notified=True）才算已通知 → 跳過。notified=False 代表
            # 「已建立但推播未成功」，需重用該 row 補推（不重複建立）。
            if existing_alert is not None and existing_alert.notified:
                continue
            tier_amount = budget.amount_ntd * tier // 100
            if current < tier_amount:
                continue
            if existing_alert is not None:
                # 補推：重用既有未通知 row，刷新累計金額。
                existing_alert.current_amount_ntd = current
                triggered.append((budget, existing_alert))
            else:
                alert = BudgetAlert(
                    budget_id=budget.id,
                    period_year_month=period,
                    threshold_breached_percent=tier,
                    current_amount_ntd=current,
                    triggered_at=datetime.now(UTC),
                    notified=False,
                )
                session.add(alert)
                await session.flush()
                triggered.append((budget, alert))

    if not triggered:
        return {"alerts_triggered": 0, "skipped": skipped}

    # 先 commit alert rows（notified 仍為 False）以保證持久化，再嘗試推播。
    await session.commit()

    settings_obj = get_settings()
    if not settings_obj.telegram_bot_token or not settings_obj.telegram_chat_id:
        logger.info(
            "Telegram disabled; %d budget alert(s) recorded without push",
            len(triggered),
        )
        return {"alerts_triggered": len(triggered), "skipped": skipped}

    text = _format_aggregated_message(period, triggered)
    try:
        await send_message(
            settings_obj.telegram_bot_token,
            settings_obj.telegram_chat_id,
            text,
        )
    except Exception as exc:  # noqa: BLE001
        # 推播失敗：notified 留 False，alert rows 已持久化，下次重跑會補推。
        logger.warning("Failed to send budget alert message: %s", exc)
        return {"alerts_triggered": len(triggered), "skipped": skipped}

    # 推播成功才標記 notified=True（補推時亦同），並 commit。
    for _budget, alert in triggered:
        alert.notified = True
    await session.commit()
    logger.info("Sent aggregated budget alert message (%d alerts)", len(triggered))

    return {"alerts_triggered": len(triggered), "skipped": skipped}
