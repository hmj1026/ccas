"""Credit Card Artifact System (CCAS) Agent CLI.

Provides read-only structured CLI commands for external agents and manual operators,
sharing canonical schemas and service functions with the Agent MCP server.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import click
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.bills import get_bill, get_payment_due, list_bills
from ccas.services.budgets import budget_status
from ccas.services.pipeline import pipeline_status
from ccas.services.schemas import (
    AgentQueryError,
    BillResult,
    BillsPage,
    BudgetStatusResult,
    PaymentDueResult,
    PipelineStatusResult,
    ServiceProjection,
    TransactionsPage,
)
from ccas.services.transactions import query_transactions


def _escape_control_chars(val: Any) -> str:
    """Escape control characters to prevent terminal escape injection."""
    if val is None:
        return ""
    s = str(val)
    out: list[str] = []
    for ch in s:
        code = ord(ch)
        if code == 9:
            out.append("  ")
        elif code in (10, 13):
            out.append(" ")
        elif code < 32 or (127 <= code <= 159):
            out.append(f"\\x{code:02x}")
        else:
            out.append(ch)
    return "".join(out)


def _render_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a text table with escaped control characters."""
    if not rows:
        return "No records found."
    escaped_headers = [_escape_control_chars(h) for h in headers]
    escaped_rows = [[_escape_control_chars(cell) for cell in row] for row in rows]
    col_widths = [len(h) for h in escaped_headers]
    for row in escaped_rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))
            else:
                col_widths.append(len(cell))
    header_line = " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(escaped_headers)
    )
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(col_widths)))
    row_lines = [
        " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row))
        for row in escaped_rows
    ]
    return "\n".join([header_line, sep_line, *row_lines])


def _render_bills_page_table(payload: BillsPage) -> str:
    headers = [
        "ID",
        "Bank",
        "Month",
        "Total Amount",
        "Due Date",
        "Paid",
        "Cards",
        "Reconciliation Key",
    ]
    rows: list[list[Any]] = []
    for b in payload.data:
        bank = b.bank_code + (f" ({b.bank_name})" if b.bank_name else "")
        cards = ",".join(b.card_last4s) if b.card_last4s else "-"
        amount = f"{b.total_amount.currency} {b.total_amount.value}"
        rows.append(
            [
                b.id,
                bank,
                b.billing_month,
                amount,
                str(b.due_date),
                "Yes" if b.is_paid else "No",
                cards,
                b.reconciliation_key,
            ]
        )
    table = _render_table(headers, rows)
    meta = payload.pagination
    return f"{table}\n\nPage {meta.page}/{meta.total_pages} (Total: {meta.total})"


def _render_bill_result_table(payload: BillResult) -> str:
    b = payload.data
    bank = b.bank_code + (f" ({b.bank_name})" if b.bank_name else "")
    cards = ",".join(b.card_last4s) if b.card_last4s else "-"
    amount = f"{b.total_amount.currency} {b.total_amount.value}"
    headers = ["Field", "Value"]
    rows: list[list[Any]] = [
        ["ID", b.id],
        ["Bank", bank],
        ["Billing Month", b.billing_month],
        ["Total Amount", amount],
        ["Due Date", str(b.due_date)],
        ["Paid", "Yes" if b.is_paid else "No"],
        ["Cards", cards],
        ["Reconciliation Key", b.reconciliation_key],
    ]
    return _render_table(headers, rows)


def _render_transactions_page_table(payload: TransactionsPage) -> str:
    headers = [
        "ID",
        "Bill ID",
        "Date",
        "Merchant",
        "Amount",
        "Category",
        "Card",
        "Installment",
        "Reconciliation Key",
    ]
    rows: list[list[Any]] = []
    for t in payload.data:
        amount = f"{t.amount.currency} {t.amount.value}"
        installment = (
            f"{t.installment_current}/{t.installment_total}"
            if t.installment_current is not None
            else "-"
        )
        rows.append(
            [
                t.id,
                t.bill_id,
                str(t.trans_date),
                t.merchant,
                amount,
                t.category or "-",
                t.card_last4 or "-",
                installment,
                t.reconciliation_key,
            ]
        )
    table = _render_table(headers, rows)
    meta = payload.pagination
    return f"{table}\n\nPage {meta.page}/{meta.total_pages} (Total: {meta.total})"


def _render_payment_due_table(payload: PaymentDueResult) -> str:
    headers = [
        "ID",
        "Bank",
        "Month",
        "Total Amount",
        "Due Date",
        "Cards",
        "Reconciliation Key",
    ]
    rows: list[list[Any]] = []
    for b in payload.data:
        bank = b.bank_code + (f" ({b.bank_name})" if b.bank_name else "")
        cards = ",".join(b.card_last4s) if b.card_last4s else "-"
        amount = f"{b.total_amount.currency} {b.total_amount.value}"
        rows.append(
            [
                b.id,
                bank,
                b.billing_month,
                amount,
                str(b.due_date),
                cards,
                b.reconciliation_key,
            ]
        )
    return _render_table(headers, rows)


def _render_budget_status_table(payload: BudgetStatusResult) -> str:
    headers = [
        "ID",
        "Scope",
        "Ref",
        "Amount",
        "Alert %",
        "Enabled",
        "Period",
        "Spent",
        "% Used",
        "Breached",
    ]
    rows: list[list[Any]] = []
    for b in payload.data:
        amount = f"{b.amount.currency} {b.amount.value}"
        cp = b.current_period
        period = cp.period_year_month if cp else "-"
        spent = f"{cp.current_amount.currency} {cp.current_amount.value}" if cp else "-"
        pct = f"{cp.percent:.1f}%" if cp else "-"
        breached = ("Yes" if cp.threshold_breached else "No") if cp else "-"
        rows.append(
            [
                b.id,
                b.scope,
                b.scope_ref or "-",
                amount,
                f"{b.alert_threshold_percent}%",
                "Yes" if b.enabled else "No",
                period,
                spent,
                pct,
                breached,
            ]
        )
    return _render_table(headers, rows)


def _render_pipeline_status_table(payload: PipelineStatusResult) -> str:
    p = payload.data
    headers = ["Field", "Value"]
    rows: list[list[Any]] = [
        ["ID", p.id],
        ["Job ID", p.job_id],
        ["Status", p.status],
        ["Triggered By", p.triggered_by],
        ["Current Stage", p.current_stage or "-"],
        ["Progress", f"{p.current_stage_processed}/{p.current_stage_total}"],
        ["Needs Human", "Yes" if p.needs_human else "No"],
        ["Error", p.error_message or "-"],
    ]
    return _render_table(headers, rows)


async def _execute_with_session[T](
    coro_factory: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    """Lazily obtain database session and ensure engine disposal finally."""
    from ccas.storage.database import get_engine, get_session_factory

    session_factory = get_session_factory()
    engine = get_engine()
    try:
        async with session_factory() as session:
            return await coro_factory(session)
    finally:
        await engine.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def _run_command[T: BaseModel](
    coro_factory: Callable[[AsyncSession], Awaitable[ServiceProjection[T]]],
    format_type: str,
    table_renderer: Callable[[T], str],
) -> None:
    """Execute service query and output JSON or table with safe error handling."""
    try:
        projection = asyncio.run(_execute_with_session(coro_factory))
    except AgentQueryError as exc:
        payload: dict[str, Any] = {
            "code": exc.code,
            "message": exc.message,
        }
        if exc.code == "needs_human":
            payload["needs_human"] = True
        if exc.data is not None:
            if isinstance(exc.data, BaseModel):
                payload["data"] = exc.data.model_dump(mode="json")
            else:
                payload["data"] = exc.data
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        sys.exit(2)
    except ValidationError:
        payload = {
            "code": "needs_human",
            "message": "Database contains invalid data; human review required.",
            "needs_human": True,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        sys.exit(2)
    except Exception:
        payload = {
            "code": "needs_human",
            "message": "Query failed; check local database configuration and retry.",
            "needs_human": True,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        sys.exit(2)

    # If pipeline retries are exhausted, raise human review error per specification
    if isinstance(projection.payload, PipelineStatusResult):
        if projection.payload.data.needs_human:
            err_payload = {
                "code": "needs_human",
                "message": (
                    "Pipeline retries are exhausted; inspect the run before retrying."
                ),
                "needs_human": True,
                "data": projection.payload.data.model_dump(mode="json"),
            }
            sys.stdout.write(json.dumps(err_payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            sys.exit(2)

    if format_type.lower() == "table":
        output = table_renderer(projection.payload)
    else:
        output = json.dumps(
            projection.payload.model_dump(mode="json"),
            ensure_ascii=False,
        )
    sys.stdout.write(output + "\n")
    sys.stdout.flush()


class OrderedGroup(click.Group):
    """Click group preserving registration order and standardizing errors."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands.keys())

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        try:
            return super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
        except click.ClickException:
            err_payload = {
                "code": "invalid_argument",
                "message": (
                    "Invalid command arguments; use --help for supported options."
                ),
            }
            sys.stdout.write(json.dumps(err_payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            sys.exit(2)
        except SystemExit:
            raise
        except AgentQueryError as exc:
            payload: dict[str, Any] = {
                "code": exc.code,
                "message": exc.message,
            }
            if exc.code == "needs_human":
                payload["needs_human"] = True
            if exc.data is not None:
                if isinstance(exc.data, BaseModel):
                    payload["data"] = exc.data.model_dump(mode="json")
                else:
                    payload["data"] = exc.data
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            sys.exit(2)
        except ValidationError:
            payload = {
                "code": "needs_human",
                "message": "Database contains invalid data; human review required.",
                "needs_human": True,
            }
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            sys.exit(2)
        except Exception:
            payload = {
                "code": "needs_human",
                "message": (
                    "Query failed; check local database configuration and retry."
                ),
                "needs_human": True,
            }
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            sys.exit(2)


@click.group(
    cls=OrderedGroup,
    help="CCAS Agent CLI - Read-only commands for credit card artifact system.",
)
def cli() -> None:
    """Agent CLI root group."""


@cli.command(
    "list-bills",
    help="List credit card bills with optional filtering and pagination.",
)
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (json or table).",
)
@click.option("--month", type=str, default=None, help="Billing month (YYYY-MM).")
@click.option("--year", type=int, default=None, help="Billing year (2000-2099).")
@click.option("--bank-code", type=str, default=None, help="Bank code.")
@click.option(
    "--status",
    type=click.Choice(["all", "paid", "unpaid"], case_sensitive=False),
    default="all",
    help="Payment status.",
)
@click.option("--page", type=int, default=1, help="Page number (>= 1).")
@click.option("--page-size", type=int, default=20, help="Page size (1-100).")
def list_bills_command(
    format_type: str,
    month: str | None,
    year: int | None,
    bank_code: str | None,
    status: str,
    page: int,
    page_size: int,
) -> None:
    async def _action(
        session: AsyncSession,
    ) -> ServiceProjection[BillsPage]:
        return await list_bills(
            session,
            month=month,
            year=year,
            bank_code=bank_code,
            status=status.lower(),
            page=page,
            page_size=page_size,
        )

    _run_command(
        _action,
        format_type=format_type,
        table_renderer=_render_bills_page_table,
    )


@cli.command("get-bill", help="Get details of a single bill by ID.")
@click.option("--bill-id", type=int, required=True, help="Bill ID.")
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (json or table).",
)
def get_bill_command(
    bill_id: int,
    format_type: str,
) -> None:
    async def _action(
        session: AsyncSession,
    ) -> ServiceProjection[BillResult]:
        return await get_bill(session, bill_id=bill_id)

    _run_command(
        _action,
        format_type=format_type,
        table_renderer=_render_bill_result_table,
    )


@cli.command(
    "query-transactions",
    help="Query transactions with optional filtering, search, and pagination.",
)
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (json or table).",
)
@click.option("--month", type=str, default=None, help="Billing month (YYYY-MM).")
@click.option("--year", type=int, default=None, help="Billing year (2000-2099).")
@click.option("--bank-code", type=str, default=None, help="Bank code.")
@click.option("--category", type=str, default=None, help="Transaction category.")
@click.option("--q", type=str, default=None, help="Search query (min 2 chars).")
@click.option(
    "--sort",
    type=click.Choice(
        [
            "trans_date_asc",
            "trans_date_desc",
            "amount_asc",
            "amount_desc",
            "merchant_asc",
            "merchant_desc",
        ],
        case_sensitive=False,
    ),
    default="trans_date_desc",
    help="Sort order.",
)
@click.option("--page", type=int, default=1, help="Page number (>= 1).")
@click.option("--page-size", type=int, default=20, help="Page size (1-100).")
def query_transactions_command(
    format_type: str,
    month: str | None,
    year: int | None,
    bank_code: str | None,
    category: str | None,
    q: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> None:
    async def _action(
        session: AsyncSession,
    ) -> ServiceProjection[TransactionsPage]:
        return await query_transactions(
            session,
            month=month,
            year=year,
            bank_code=bank_code,
            category=category,
            q=q,
            sort=sort.lower(),
            page=page,
            page_size=page_size,
        )

    _run_command(
        _action,
        format_type=format_type,
        table_renderer=_render_transactions_page_table,
    )


@cli.command(
    "get-payment-due",
    help="List all unpaid bills ordered by due date ascending.",
)
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (json or table).",
)
def get_payment_due_command(
    format_type: str,
) -> None:
    async def _action(
        session: AsyncSession,
    ) -> ServiceProjection[PaymentDueResult]:
        return await get_payment_due(session)

    _run_command(
        _action,
        format_type=format_type,
        table_renderer=_render_payment_due_table,
    )


@cli.command(
    "budget-status",
    help="Get budget statuses with optional current period spending.",
)
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (json or table).",
)
@click.option(
    "--scope",
    type=click.Choice(
        ["monthly_total", "monthly_category", "monthly_bank"],
        case_sensitive=False,
    ),
    default=None,
    help="Budget scope.",
)
@click.option(
    "--include-current-period",
    is_flag=True,
    default=False,
    help="Include current period spending aggregation.",
)
def budget_status_command(
    format_type: str,
    scope: str | None,
    include_current_period: bool,
) -> None:
    async def _action(
        session: AsyncSession,
    ) -> ServiceProjection[BudgetStatusResult]:
        return await budget_status(
            session,
            scope=scope.lower() if scope else None,
            include_current_period=include_current_period,
        )

    _run_command(
        _action,
        format_type=format_type,
        table_renderer=_render_budget_status_table,
    )


@cli.command(
    "pipeline-status",
    help="Get status of the most recent pipeline run.",
)
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (json or table).",
)
def pipeline_status_command(
    format_type: str,
) -> None:
    async def _action(
        session: AsyncSession,
    ) -> ServiceProjection[PipelineStatusResult]:
        return await pipeline_status(session)

    _run_command(
        _action,
        format_type=format_type,
        table_renderer=_render_pipeline_status_table,
    )


def main(args: Sequence[str] | None = None) -> None:
    """Entry point for the ccas-agent console application."""
    cli.main(args=args)


if __name__ == "__main__":
    main()
