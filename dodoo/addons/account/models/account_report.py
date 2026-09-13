"""Financial reports (spec 003, US-8 / FR-036…FR-040).

All figures come from **posted** journal lines only, exclude section/note display
lines, and honour an optional date range (Balance Sheet / Aged use a single
"as of" date). Sign convention follows the ledger: ``balance = debit - credit``,
so asset/expense accounts carry a positive net and liability/equity/income a
negative one. Each report flips signs where a human expects a positive magnitude
(income on the P&L, liabilities on the Balance Sheet, …), mirroring Odoo's
presentation.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_POSTED = "state='posted'"
_REAL_LINE = "ml.display_type NOT IN ('line_section','line_note')"

_INCOME_TYPES = ("income", "income_other")
_COST_TYPES = ("expense_direct_cost",)
_EXPENSE_TYPES = ("expense", "expense_other", "expense_depreciation")
_PL_TYPES = _INCOME_TYPES + _COST_TYPES + _EXPENSE_TYPES


def _d(value: Any) -> Decimal:
    return Decimal(str(value if value is not None else "0"))


def _as_date(value: str | datetime.date | None) -> datetime.date | None:
    """asyncpg wants real ``date`` objects for DATE params, not ISO strings."""
    if value is None or isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


class _VirtualReport(BaseModel):
    """Base for virtual report models (no DB table)."""

    _abstract = True
    _name: str = ""

    @classmethod
    async def search_read(
        cls, env, domain=None, fields=None, offset=0, limit=None, order=None
    ):
        return []

    @classmethod
    def fields_get(cls, allfields=None, attributes=None):
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Trial Balance — FR-036
# ─────────────────────────────────────────────────────────────────────────────
class AccountReportTrialBalance(_VirtualReport):
    _abstract = False
    _name = "account.report.trial.balance"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        date_from: str | datetime.date | None = None,
        date_to: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        df, dt = _as_date(date_from), _as_date(date_to)
        where_company = ""
        base_params: dict[str, Any] = {}
        if company_id:
            where_company = " AND a.company_id = :company_id"
            base_params["company_id"] = company_id

        period_where = where_company
        period_params = dict(base_params)
        if df:
            period_where += " AND m.date >= :date_from"
            period_params["date_from"] = df
        if dt:
            period_where += " AND m.date <= :date_to"
            period_params["date_to"] = dt

        sql = f"""
            SELECT
                a.id AS account_id,
                a.code,
                a.name,
                a.account_type,
                ROUND(SUM(ml.debit)::NUMERIC, 2)            AS debit,
                ROUND(SUM(ml.credit)::NUMERIC, 2)           AS credit
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            WHERE m.{_POSTED} AND {_REAL_LINE} {period_where}
            GROUP BY a.id, a.code, a.name, a.account_type
            ORDER BY a.code
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), period_params)
            by_account = {r["account_id"]: dict(r._mapping) for r in rows}

        # FR-034, ADR-044: each account's opening balance is everything posted
        # strictly before `date_from` — merged in as a starting point rather
        # than a second query shape.
        opening_map: dict[int, Decimal] = {}
        if df:
            opening_sql = f"""
                SELECT a.id AS account_id, a.code, a.name, a.account_type,
                       ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance
                FROM account_move_line ml
                JOIN account_account a ON a.id = ml.account_id
                JOIN account_move m ON m.id = ml.move_id
                WHERE m.{_POSTED} AND {_REAL_LINE} AND m.date < :date_from {where_company}
                GROUP BY a.id, a.code, a.name, a.account_type
            """
            opening_params = dict(base_params)
            opening_params["date_from"] = df
            async with env.dml_conn() as conn:
                orows = await conn.execute(text(opening_sql), opening_params)
                for r in orows:
                    rm = dict(r._mapping)
                    opening_map[rm["account_id"]] = _d(rm["balance"])
                    # An account with pre-period activity but none in the
                    # filtered period must still appear (with 0 debit/credit).
                    by_account.setdefault(
                        rm["account_id"],
                        {
                            "account_id": rm["account_id"],
                            "code": rm["code"],
                            "name": rm["name"],
                            "account_type": rm["account_type"],
                            "debit": Decimal("0"),
                            "credit": Decimal("0"),
                        },
                    )

        lines = []
        for account_id, r in by_account.items():
            debit = _d(r["debit"])
            credit = _d(r["credit"])
            opening = opening_map.get(account_id, Decimal("0"))
            if debit == 0 and credit == 0 and opening == 0:
                continue
            lines.append(
                {
                    "account_id": account_id,
                    "code": r["code"],
                    "name": r["name"],
                    "account_type": r["account_type"],
                    "opening_balance": str(opening),
                    "debit": str(debit),
                    "credit": str(credit),
                    "balance": str(opening + debit - credit),
                }
            )
        lines.sort(key=lambda x: x["code"])

        total_debit = sum((_d(line["debit"]) for line in lines), Decimal("0"))
        total_credit = sum((_d(line["credit"]) for line in lines), Decimal("0"))
        return {
            "lines": lines,
            "totals": {
                "debit": str(total_debit),
                "credit": str(total_credit),
                "balanced": abs(total_debit - total_credit) < Decimal("0.01"),
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# General Ledger — FR-037
# ─────────────────────────────────────────────────────────────────────────────
class AccountReportGeneralLedger(_VirtualReport):
    _abstract = False
    _name = "account.report.general.ledger"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        account_id: int | None = None,
        date_from: str | datetime.date | None = None,
        date_to: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        df, dt = _as_date(date_from), _as_date(date_to)
        params: dict[str, Any] = {}
        where = ""
        if account_id:
            where += " AND ml.account_id = :account_id"
            params["account_id"] = account_id
        if df:
            where += " AND m.date >= :date_from"
            params["date_from"] = df
        if dt:
            where += " AND m.date <= :date_to"
            params["date_to"] = dt
        if company_id:
            where += " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT
                a.id   AS account_id,
                a.code AS account_code,
                a.name AS account_name,
                m.id   AS move_id,
                m.date,
                m.name AS move_name,
                p.name AS partner_name,
                ml.name AS label,
                ROUND(ml.debit::NUMERIC, 2)  AS debit,
                ROUND(ml.credit::NUMERIC, 2) AS credit,
                ROUND(SUM(ml.debit - ml.credit) OVER (
                    PARTITION BY ml.account_id ORDER BY m.date, ml.id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )::NUMERIC, 2) AS running_balance
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            LEFT JOIN res_partner p ON p.id = ml.partner_id
            WHERE m.{_POSTED} AND {_REAL_LINE} {where}
            ORDER BY a.code, a.id, m.date, ml.id
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            raw = [dict(r._mapping) for r in rows]

        # FR-034, ADR-044: each account's opening balance (everything posted
        # strictly before `date_from`) becomes the running-balance window's
        # starting value instead of 0.
        opening_map: dict[int, Decimal] = {}
        if df:
            opening_where = ""
            opening_params: dict[str, Any] = {"date_from": df}
            if account_id:
                opening_where += " AND ml.account_id = :account_id"
                opening_params["account_id"] = account_id
            if company_id:
                opening_where += " AND a.company_id = :company_id"
                opening_params["company_id"] = company_id
            opening_sql = f"""
                SELECT a.id AS account_id,
                       ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance
                FROM account_move_line ml
                JOIN account_account a ON a.id = ml.account_id
                JOIN account_move m ON m.id = ml.move_id
                WHERE m.{_POSTED} AND {_REAL_LINE} AND m.date < :date_from {opening_where}
                GROUP BY a.id
            """
            async with env.dml_conn() as conn:
                orows = await conn.execute(text(opening_sql), opening_params)
                opening_map = {r[0]: _d(r[1]) for r in orows}

        # Group into per-account sections with an opening/closing balance.
        accounts: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        for r in raw:
            if cur is None or cur["account_id"] != r["account_id"]:
                opening = opening_map.get(r["account_id"], Decimal("0"))
                cur = {
                    "account_id": r["account_id"],
                    "code": r["account_code"],
                    "name": r["account_name"],
                    "opening_balance": opening,
                    "lines": [],
                    "total_debit": Decimal("0"),
                    "total_credit": Decimal("0"),
                }
                accounts.append(cur)
            cur["total_debit"] += _d(r["debit"])
            cur["total_credit"] += _d(r["credit"])
            cur["lines"].append(
                {
                    "move_id": r["move_id"],
                    "date": r["date"].isoformat() if r["date"] else None,
                    "move_name": r["move_name"],
                    "partner_name": r["partner_name"],
                    "label": r["label"],
                    "debit": str(_d(r["debit"])),
                    "credit": str(_d(r["credit"])),
                    "running_balance": str(cur["opening_balance"] + _d(r["running_balance"])),
                }
            )

        grand_debit = sum((a["total_debit"] for a in accounts), Decimal("0"))
        grand_credit = sum((a["total_credit"] for a in accounts), Decimal("0"))
        return {
            "accounts": [
                {
                    "account_id": a["account_id"],
                    "code": a["code"],
                    "name": a["name"],
                    "opening_balance": str(a["opening_balance"]),
                    "lines": a["lines"],
                    "total_debit": str(a["total_debit"]),
                    "total_credit": str(a["total_credit"]),
                    "balance": str(a["opening_balance"] + a["total_debit"] - a["total_credit"]),
                }
                for a in accounts
            ],
            "totals": {"debit": str(grand_debit), "credit": str(grand_credit)},
        }


async def _pl_rows(
    env: Environment,
    types: tuple[str, ...],
    date_from: datetime.date | None,
    date_to: datetime.date | None,
    company_id: int | None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"types": list(types)}
    where = ""
    if date_from:
        where += " AND m.date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        where += " AND m.date <= :date_to"
        params["date_to"] = date_to
    if company_id:
        where += " AND a.company_id = :company_id"
        params["company_id"] = company_id
    sql = f"""
        SELECT a.id AS account_id, a.code, a.name, a.account_type,
               ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance,
               MAX(ml.move_id) AS move_id
        FROM account_move_line ml
        JOIN account_account a ON a.id = ml.account_id
        JOIN account_move m ON m.id = ml.move_id
        WHERE m.{_POSTED} AND {_REAL_LINE}
          AND a.account_type = ANY(:types) {where}
        GROUP BY a.id, a.code, a.name, a.account_type
        HAVING SUM(ml.debit - ml.credit) <> 0
        ORDER BY a.code
    """
    async with env.dml_conn() as conn:
        rows = await conn.execute(text(sql), params)
        return [dict(r._mapping) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Profit & Loss — FR-038
# ─────────────────────────────────────────────────────────────────────────────
class AccountReportProfitLoss(_VirtualReport):
    _abstract = False
    _name = "account.report.profit.loss"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        date_from: str | datetime.date | None = None,
        date_to: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        df, dt = _as_date(date_from), _as_date(date_to)
        rows = await _pl_rows(env, _PL_TYPES, df, dt, company_id)

        def _section(types: tuple[str, ...], flip: bool) -> dict[str, Any]:
            sign = Decimal("-1") if flip else Decimal("1")
            lines = [
                {
                    "account_id": r["account_id"],
                    "move_id": r["move_id"],
                    "code": r["code"],
                    "name": r["name"],
                    "amount": str(sign * _d(r["balance"])),
                }
                for r in rows
                if r["account_type"] in types
            ]
            total = sum((_d(line["amount"]) for line in lines), Decimal("0"))
            return {"lines": lines, "total": str(total)}

        income = _section(_INCOME_TYPES, flip=True)
        cost = _section(_COST_TYPES, flip=False)
        expense = _section(_EXPENSE_TYPES, flip=False)
        gross = _d(income["total"]) - _d(cost["total"])
        net = gross - _d(expense["total"])
        return {
            "sections": {
                "income": income,
                "cost_of_revenue": cost,
                "gross_profit": str(gross),
                "expenses": expense,
                "net_profit": str(net),
            },
            "date_from": df.isoformat() if df else None,
            "date_to": dt.isoformat() if dt else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Balance Sheet — FR-039
# ─────────────────────────────────────────────────────────────────────────────
_BS_GROUPS = [
    ("current_assets", ("asset_receivable", "asset_cash", "asset_current", "asset_prepayments"), False),
    ("fixed_assets", ("asset_fixed", "asset_non_current"), False),
    ("current_liabilities", ("liability_payable", "liability_credit_card", "liability_current"), True),
    ("non_current_liabilities", ("liability_non_current",), True),
    ("equity", ("equity", "equity_unaffected"), True),
]


def _fiscal_year_end(year: int, last_month: int, last_day: int) -> datetime.date:
    import calendar

    max_day = calendar.monthrange(year, last_month)[1]
    return datetime.date(year, last_month, min(last_day, max_day))


def company_fiscal_year_start(
    as_of: datetime.date, last_month: int = 12, last_day: int = 31
) -> datetime.date:
    """FR-037, ADR-044: the first day of the fiscal year containing ``as_of``,
    given the company's fiscal-year-end month/day (default 12/31 — the
    calendar year, matching Odoo's own default)."""
    this_year_end = _fiscal_year_end(as_of.year, last_month, last_day)
    boundary_year = as_of.year if as_of <= this_year_end else as_of.year + 1
    prev_year_end = _fiscal_year_end(boundary_year - 1, last_month, last_day)
    return prev_year_end + datetime.timedelta(days=1)


async def _company_fiscal_year_columns(
    env: Environment, company_id: int | None
) -> tuple[int, int]:
    if not company_id:
        return 12, 31
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT fiscalyear_last_month, fiscalyear_last_day "
                "FROM res_company WHERE id = :cid"
            ),
            {"cid": company_id},
        )
        r = row.fetchone()
    if not r or r[0] is None or r[1] is None:
        return 12, 31
    return int(r[0]), int(r[1])


class AccountReportBalanceSheet(_VirtualReport):
    _abstract = False
    _name = "account.report.balance.sheet"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        date: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        as_of = _as_date(date) or datetime.date.today()
        params: dict[str, Any] = {"as_of": as_of}
        where_company = ""
        if company_id:
            where_company = " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT a.id AS account_id, a.code, a.name, a.account_type,
                   ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance,
                   MAX(ml.move_id) AS move_id
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            WHERE m.{_POSTED} AND {_REAL_LINE}
              AND m.date <= :as_of {where_company}
            GROUP BY a.id, a.code, a.name, a.account_type
            HAVING SUM(ml.debit - ml.credit) <> 0
            ORDER BY a.code
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            data = [dict(r._mapping) for r in rows]

        def _group(types: tuple[str, ...], flip: bool) -> dict[str, Any]:
            sign = Decimal("-1") if flip else Decimal("1")
            lines = [
                {
                    "account_id": r["account_id"],
                    "move_id": r["move_id"],
                    "code": r["code"],
                    "name": r["name"],
                    "amount": str(sign * _d(r["balance"])),
                }
                for r in data
                if r["account_type"] in types
            ]
            total = sum((_d(x["amount"]) for x in lines), Decimal("0"))
            return {"lines": lines, "total": str(total)}

        groups = {key: _group(types, flip) for key, types, flip in _BS_GROUPS}

        # FR-037, ADR-044: current-year earnings = the P&L result from the
        # start of the fiscal year containing `as_of` (not all-time), so
        # `equity_unaffected` can correctly accumulate prior years' results
        # once `close_fiscal_year` has run.
        last_month, last_day = await _company_fiscal_year_columns(env, company_id)
        fy_start = company_fiscal_year_start(as_of, last_month, last_day)
        pl = await _pl_rows(env, _PL_TYPES, fy_start, as_of, company_id)
        cye = -sum((_d(r["balance"]) for r in pl), Decimal("0"))

        assets_total = _d(groups["current_assets"]["total"]) + _d(groups["fixed_assets"]["total"])
        liabilities_total = (
            _d(groups["current_liabilities"]["total"])
            + _d(groups["non_current_liabilities"]["total"])
        )
        equity_total = _d(groups["equity"]["total"]) + cye
        return {
            "groups": groups,
            "current_year_earnings": str(cye),
            "totals": {
                "assets": str(assets_total),
                "liabilities": str(liabilities_total),
                "equity": str(equity_total),
                "liabilities_and_equity": str(liabilities_total + equity_total),
                "balanced": abs(assets_total - (liabilities_total + equity_total)) < Decimal("0.01"),
            },
            "as_of": as_of.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Aged Receivable / Payable — FR-040
# ─────────────────────────────────────────────────────────────────────────────
_BUCKETS = ("current", "b_0_30", "b_31_60", "b_61_90", "b_90_plus")


class AccountReportAgedReceivable(_VirtualReport):
    _abstract = False
    _name = "account.report.aged.receivable"

    @classmethod
    async def get_report(cls, env, date=None, company_id=None):
        return await _aged_report(env, "asset_receivable", date, company_id)


class AccountReportAgedPayable(_VirtualReport):
    _abstract = False
    _name = "account.report.aged.payable"

    @classmethod
    async def get_report(cls, env, date=None, company_id=None):
        return await _aged_report(env, "liability_payable", date, company_id)


def _bucket_for(days: int) -> str:
    """FR-036, ADR-044: a not-yet-due balance (``days <= 0``) is "current",
    distinct from the first overdue bucket — it no longer gets clamped into
    ``b_0_30``."""
    if days <= 0:
        return "current"
    if days <= 30:
        return "b_0_30"
    if days <= 60:
        return "b_31_60"
    if days <= 90:
        return "b_61_90"
    return "b_90_plus"


async def _aged_report(
    env: Environment,
    account_type: str,
    date: str | datetime.date | None = None,
    company_id: int | None = None,
) -> dict[str, Any]:
    as_of = _as_date(date) or datetime.date.today()
    params: dict[str, Any] = {"atype": account_type, "as_of": as_of}
    where_company = ""
    if company_id:
        where_company = " AND a.company_id = :company_id"
        params["company_id"] = company_id

    sql = f"""
        SELECT
            COALESCE(p.name, '—') AS partner_name,
            a.id AS account_id,
            m.id AS move_id,
            ROUND(ABS(ml.amount_residual)::NUMERIC, 2) AS residual,
            m.invoice_date_due AS due_date,
            (CAST(:as_of AS DATE) - COALESCE(m.invoice_date_due, m.date))::INTEGER AS days_overdue
        FROM account_move_line ml
        JOIN account_account a ON a.id = ml.account_id
        JOIN account_move m ON m.id = ml.move_id
        LEFT JOIN res_partner p ON p.id = ml.partner_id
        WHERE m.{_POSTED}
          AND ml.display_type = 'payment_term'
          AND a.account_type = :atype
          AND ABS(ml.amount_residual) > 0
          AND m.date <= :as_of
          {where_company}
        ORDER BY partner_name, m.invoice_date_due
    """
    async with env.dml_conn() as conn:
        rows = await conn.execute(text(sql), params)
        raw = [dict(r._mapping) for r in rows]

    partners: dict[str, dict[str, Any]] = {}
    grand = {b: Decimal("0") for b in _BUCKETS}
    grand_total = Decimal("0")
    for r in raw:
        days = int(r["days_overdue"] or 0)
        bucket = _bucket_for(days)
        residual = _d(r["residual"])
        name = r["partner_name"]
        p = partners.setdefault(
            name,
            {
                "partner_name": name,
                "account_id": r["account_id"],
                # FR-035: one representative move per bucket, for drill-down
                # to a specific entry (a partner/bucket can span several).
                "bucket_move_ids": {},
                **{b: Decimal("0") for b in _BUCKETS},
                "total": Decimal("0"),
            },
        )
        p[bucket] += residual
        p["total"] += residual
        p["bucket_move_ids"].setdefault(bucket, r["move_id"])
        grand[bucket] += residual
        grand_total += residual

    return {
        "partners": [
            {
                "partner_name": p["partner_name"],
                "account_id": p["account_id"],
                "bucket_move_ids": p["bucket_move_ids"],
                **{b: str(p[b]) for b in _BUCKETS},
                "total": str(p["total"]),
            }
            for p in sorted(partners.values(), key=lambda x: x["partner_name"])
        ],
        "totals": {**{b: str(grand[b]) for b in _BUCKETS}, "total": str(grand_total)},
        "as_of": as_of.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tax Report — FR-016, ADR-040/044
# ─────────────────────────────────────────────────────────────────────────────
class AccountReportTax(_VirtualReport):
    """Aggregates posted invoice/bill tax and base amounts by
    ``account.account.tag`` (the tax-grid tags US1/ADR-040 attached to
    ``account.tax.repartition.line``)."""

    _abstract = False
    _name = "account.report.tax"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        date_from: str | datetime.date | None = None,
        date_to: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        df, dt = _as_date(date_from), _as_date(date_to)
        params: dict[str, Any] = {}
        where = ""
        if df:
            where += " AND m.date >= :date_from"
            params["date_from"] = df
        if dt:
            where += " AND m.date <= :date_to"
            params["date_to"] = dt
        if company_id:
            where += " AND m.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT tag.id AS tag_id, tag.name AS tag_name,
                   ROUND(SUM(
                       CASE WHEN rl.repartition_type = 'tax' THEN ABS(ml.balance) ELSE 0 END
                   )::NUMERIC, 2) AS tax_amount,
                   ROUND(SUM(
                       CASE WHEN rl.repartition_type = 'base' THEN ABS(ml.tax_base_amount) ELSE 0 END
                   )::NUMERIC, 2) AS base_amount
            FROM account_move_line ml
            JOIN account_move m ON m.id = ml.move_id
            JOIN account_tax_repartition_line rl
                ON rl.tax_id = ml.tax_line_id AND rl.document_type = 'invoice'
            JOIN account_tax_repartition_line_tag_rel rel ON rel.repartition_line_id = rl.id
            JOIN account_account_tag tag ON tag.id = rel.tag_id
            WHERE m.{_POSTED} AND ml.display_type = 'tax' {where}
            GROUP BY tag.id, tag.name
            ORDER BY tag.name
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            lines = [dict(r._mapping) for r in rows]

        total_tax = sum((_d(r["tax_amount"]) for r in lines), Decimal("0"))
        total_base = sum((_d(r["base_amount"]) for r in lines), Decimal("0"))
        return {
            "lines": [
                {
                    "tag_id": r["tag_id"],
                    "tag_name": r["tag_name"],
                    "base_amount": str(_d(r["base_amount"])),
                    "tax_amount": str(_d(r["tax_amount"])),
                }
                for r in lines
            ],
            "totals": {"base_amount": str(total_base), "tax_amount": str(total_tax)},
            "date_from": df.isoformat() if df else None,
            "date_to": dt.isoformat() if dt else None,
        }
