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
        params: dict[str, Any] = {}
        where = ""
        if date_from:
            where += " AND m.date >= :date_from"
            params["date_from"] = _as_date(date_from)
        if date_to:
            where += " AND m.date <= :date_to"
            params["date_to"] = _as_date(date_to)
        if company_id:
            where += " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT
                a.code,
                a.name,
                a.account_type,
                ROUND(SUM(ml.debit)::NUMERIC, 2)            AS debit,
                ROUND(SUM(ml.credit)::NUMERIC, 2)           AS credit,
                ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            WHERE m.{_POSTED} AND {_REAL_LINE} {where}
            GROUP BY a.id, a.code, a.name, a.account_type
            HAVING SUM(ml.debit) <> 0 OR SUM(ml.credit) <> 0
            ORDER BY a.code
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            lines = [dict(r._mapping) for r in rows]

        total_debit = sum((_d(r["debit"]) for r in lines), Decimal("0"))
        total_credit = sum((_d(r["credit"]) for r in lines), Decimal("0"))
        return {
            "lines": [
                {
                    "code": r["code"],
                    "name": r["name"],
                    "account_type": r["account_type"],
                    "debit": str(_d(r["debit"])),
                    "credit": str(_d(r["credit"])),
                    "balance": str(_d(r["balance"])),
                }
                for r in lines
            ],
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
        params: dict[str, Any] = {}
        where = ""
        if account_id:
            where += " AND ml.account_id = :account_id"
            params["account_id"] = account_id
        if date_from:
            where += " AND m.date >= :date_from"
            params["date_from"] = _as_date(date_from)
        if date_to:
            where += " AND m.date <= :date_to"
            params["date_to"] = _as_date(date_to)
        if company_id:
            where += " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT
                a.id   AS account_id,
                a.code AS account_code,
                a.name AS account_name,
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

        # Group into per-account sections with an opening/closing balance.
        accounts: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        for r in raw:
            if cur is None or cur["account_id"] != r["account_id"]:
                cur = {
                    "account_id": r["account_id"],
                    "code": r["account_code"],
                    "name": r["account_name"],
                    "lines": [],
                    "total_debit": Decimal("0"),
                    "total_credit": Decimal("0"),
                }
                accounts.append(cur)
            cur["total_debit"] += _d(r["debit"])
            cur["total_credit"] += _d(r["credit"])
            cur["lines"].append(
                {
                    "date": r["date"].isoformat() if r["date"] else None,
                    "move_name": r["move_name"],
                    "partner_name": r["partner_name"],
                    "label": r["label"],
                    "debit": str(_d(r["debit"])),
                    "credit": str(_d(r["credit"])),
                    "running_balance": str(_d(r["running_balance"])),
                }
            )

        grand_debit = sum((a["total_debit"] for a in accounts), Decimal("0"))
        grand_credit = sum((a["total_credit"] for a in accounts), Decimal("0"))
        return {
            "accounts": [
                {
                    "code": a["code"],
                    "name": a["name"],
                    "lines": a["lines"],
                    "total_debit": str(a["total_debit"]),
                    "total_credit": str(a["total_credit"]),
                    "balance": str(a["total_debit"] - a["total_credit"]),
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
        SELECT a.code, a.name, a.account_type,
               ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance
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
                {"code": r["code"], "name": r["name"], "amount": str(sign * _d(r["balance"]))}
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
            SELECT a.code, a.name, a.account_type,
                   ROUND(SUM(ml.debit - ml.credit)::NUMERIC, 2) AS balance
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
                {"code": r["code"], "name": r["name"], "amount": str(sign * _d(r["balance"]))}
                for r in data
                if r["account_type"] in types
            ]
            total = sum((_d(x["amount"]) for x in lines), Decimal("0"))
            return {"lines": lines, "total": str(total)}

        groups = {key: _group(types, flip) for key, types, flip in _BS_GROUPS}

        # Current-year earnings = the P&L result up to the as-of date, sitting in equity.
        pl = await _pl_rows(env, _PL_TYPES, None, as_of, company_id)
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
_BUCKETS = ("b_0_30", "b_31_60", "b_61_90", "b_90_plus")


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
        days = max(int(r["days_overdue"] or 0), 0)
        bucket = _bucket_for(days)
        residual = _d(r["residual"])
        name = r["partner_name"]
        p = partners.setdefault(
            name, {"partner_name": name, **{b: Decimal("0") for b in _BUCKETS}, "total": Decimal("0")}
        )
        p[bucket] += residual
        p["total"] += residual
        grand[bucket] += residual
        grand_total += residual

    return {
        "partners": [
            {
                "partner_name": p["partner_name"],
                **{b: str(p[b]) for b in _BUCKETS},
                "total": str(p["total"]),
            }
            for p in sorted(partners.values(), key=lambda x: x["partner_name"])
        ],
        "totals": {**{b: str(grand[b]) for b in _BUCKETS}, "total": str(grand_total)},
        "as_of": as_of.isoformat(),
    }
