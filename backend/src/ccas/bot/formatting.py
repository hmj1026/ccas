"""Bot 訊息格式化模組。

將查詢結果轉換為 Telegram 適用的純文字摘要。
所有函式皆為純函式，不存取 DB 或外部服務。
"""

from collections.abc import Sequence
from datetime import date

from ccas.storage.models import Bill


def format_status(
    bills: Sequence[Bill],
    bank_names: dict[str, str],
    *,
    filter_label: str = "全部",
) -> str:
    """格式化帳單狀態回覆，依銀行分組。

    Args:
        bills: 帳單清單。
        bank_names: bank_code → bank_name 對照。
        filter_label: 篩選條件標籤（全部/未繳/已繳）。

    Returns:
        格式化的訊息文字。
    """
    if not bills:
        return f"本月沒有{filter_label}的帳單。"

    grouped = _group_by_bank(bills)
    lines: list[str] = [f"本月帳單（{filter_label}）："]

    for bank_code, bank_bills in grouped:
        name = bank_names.get(bank_code, bank_code)
        subtotal = sum(b.total_amount for b in bank_bills)
        lines.append(f"\n{name}（小計 ${subtotal:,}）")
        for b in bank_bills:
            paid_mark = "v" if b.is_paid else "x"
            lines.append(
                f"  [{paid_mark}] #{b.id} ${b.total_amount:,} 到期 {b.due_date}"
            )

    total = sum(b.total_amount for b in bills)
    lines.append(f"\n合計：${total:,}")
    return "\n".join(lines)


def format_upcoming(bills: Sequence[Bill], bank_names: dict[str, str]) -> str:
    """格式化即將到期帳單回覆。

    Args:
        bills: 即將到期的未繳帳單清單。
        bank_names: bank_code → bank_name 對照。

    Returns:
        格式化的訊息文字。
    """
    if not bills:
        return "未來 7 天沒有即將到期的未繳帳單。"

    lines: list[str] = ["未來 7 天到期帳單："]
    for b in bills:
        name = bank_names.get(b.bank_code, b.bank_code)
        days_left = (b.due_date - date.today()).days
        lines.append(
            f"  #{b.id} {name} ${b.total_amount:,} "
            f"到期 {b.due_date}（{days_left} 天後）"
        )
    total = sum(b.total_amount for b in bills)
    lines.append(f"\n合計：${total:,}")
    return "\n".join(lines)


def format_summary(
    bills: Sequence[Bill],
    bank_names: dict[str, str],
    billing_month: str,
) -> str:
    """格式化月份消費摘要，依銀行分組。

    Args:
        bills: 指定月份的帳單清單。
        bank_names: bank_code → bank_name 對照。
        billing_month: 月份字串（YYYY-MM）。

    Returns:
        格式化的訊息文字。
    """
    if not bills:
        return f"{billing_month} 沒有帳單資料。"

    grouped = _group_by_bank(bills)
    lines: list[str] = [f"{billing_month} 消費摘要："]

    for bank_code, bank_bills in grouped:
        name = bank_names.get(bank_code, bank_code)
        subtotal = sum(b.total_amount for b in bank_bills)
        paid_count = sum(1 for b in bank_bills if b.is_paid)
        total_count = len(bank_bills)
        lines.append(f"\n{name}（${subtotal:,}，已繳 {paid_count}/{total_count}）")
        for b in bank_bills:
            paid_mark = "v" if b.is_paid else "x"
            lines.append(f"  [{paid_mark}] #{b.id} ${b.total_amount:,}")

    total = sum(b.total_amount for b in bills)
    lines.append(f"\n合計：${total:,}")
    return "\n".join(lines)


def format_category_summary(
    rows: Sequence[tuple[str, int]],
    billing_month: str,
) -> str:
    """格式化分類分布回覆。

    Args:
        rows: ``(category, total_amount)`` tuple 清單。
        billing_month: 月份字串（YYYY-MM）。

    Returns:
        格式化的訊息文字。
    """
    if not rows:
        return f"{billing_month} 沒有消費資料。"

    total = sum(amount for _, amount in rows)
    lines: list[str] = [f"{billing_month} 分類分布："]
    for category, amount in rows:
        pct = amount / total * 100 if total > 0 else 0
        lines.append(f"  {category}：${amount:,}（{pct:.1f}%）")
    lines.append(f"\n合計：${total:,}")
    return "\n".join(lines)


def format_paid_success(bill: Bill, bank_names: dict[str, str]) -> str:
    """格式化標記已繳成功的回覆。"""
    name = bank_names.get(bill.bank_code, bill.bank_code)
    return f"已標記 #{bill.id}（{name} ${bill.total_amount:,}）為已繳。"


def format_paid_already(bill: Bill, bank_names: dict[str, str]) -> str:
    """格式化帳單已是已繳狀態的回覆。"""
    name = bank_names.get(bill.bank_code, bill.bank_code)
    return f"#{bill.id}（{name} ${bill.total_amount:,}）已經是已繳狀態。"


def _group_by_bank(
    bills: Sequence[Bill],
) -> list[tuple[str, list[Bill]]]:
    """依 bank_code 分組，保持原始排序。"""
    groups: dict[str, list[Bill]] = {}
    for b in bills:
        groups.setdefault(b.bank_code, []).append(b)
    return list(groups.items())
