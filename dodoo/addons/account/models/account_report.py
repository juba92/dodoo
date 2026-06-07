from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_POSTED = "state='posted'"


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
        where_date = ""
        if date_from:
            where_date += " AND m.date >= :date_from"
            params["date_from"] = date_from
        if date_to:
            where_date += " AND m.date <= :date_to"
            params["date_to"] = date_to
        if company_id:
            where_date += " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT
                a.code,
                a.name,
                a.account_type,
                ROUND(SUM(ml.debit)::NUMERIC, 2)   AS total_debit,
                ROUND(SUM(ml.credit)::NUMERIC, 2)  AS total_credit,
                ROUND(SUM(ml.balance)::NUMERIC, 2) AS net_balance
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            WHERE m.{_POSTED}
              AND ml.display_type NOT IN ('line_section','line_note')
              {where_date}
            GROUP BY a.id, a.code, a.name, a.account_type
            ORDER BY a.code
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            result = [dict(row._mapping) for row in rows]

        total_debit = sum(Decimal(str(r["total_debit"])) for r in result)
        total_credit = sum(Decimal(str(r["total_credit"])) for r in result)
        balanced = abs(total_debit - total_credit) < Decimal("0.01")

        return {
            "result": result,
            "totals": {
                "total_debit": str(total_debit),
                "total_credit": str(total_credit),
                "balanced": balanced,
            },
        }


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
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        where = ""
        if account_id:
            where += " AND ml.account_id = :account_id"
            params["account_id"] = account_id
        if date_from:
            where += " AND m.date >= :date_from"
            params["date_from"] = date_from
        if date_to:
            where += " AND m.date <= :date_to"
            params["date_to"] = date_to

        sql = f"""
            SELECT
                m.date,
                m.name AS move_name,
                p.name AS partner_name,
                ml.name AS line_name,
                ROUND(ml.debit::NUMERIC, 2) AS debit,
                ROUND(ml.credit::NUMERIC, 2) AS credit,
                ROUND(SUM(ml.balance) OVER (
                    PARTITION BY ml.account_id ORDER BY m.date, ml.id
                )::NUMERIC, 2) AS running_balance
            FROM account_move_line ml
            JOIN account_move m ON m.id = ml.move_id
            LEFT JOIN res_partner p ON p.id = ml.partner_id
            WHERE m.{_POSTED}
              AND ml.display_type NOT IN ('line_section','line_note')
              {where}
            ORDER BY m.date, ml.id
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            result = [dict(row._mapping) for row in rows]

        return {"result": result}


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
        params: dict[str, Any] = {}
        where_date = ""
        if date_from:
            where_date += " AND m.date >= :date_from"
            params["date_from"] = date_from
        if date_to:
            where_date += " AND m.date <= :date_to"
            params["date_to"] = date_to
        if company_id:
            where_date += " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT
                a.account_type,
                a.code,
                a.name,
                ROUND(SUM(ml.balance)::NUMERIC, 2) AS net_amount
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            WHERE m.{_POSTED}
              AND ml.display_type NOT IN ('line_section','line_note')
              AND a.account_type IN (
                  'income','income_other','expense','expense_other',
                  'expense_depreciation','expense_direct_cost'
              )
              {where_date}
            GROUP BY a.id, a.code, a.name, a.account_type
            ORDER BY a.code
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            accounts = [dict(row._mapping) for row in rows]

        income = sum(
            Decimal(str(r["net_amount"]))
            for r in accounts
            if r["account_type"] in ("income", "income_other")
        )
        expense = sum(
            Decimal(str(r["net_amount"]))
            for r in accounts
            if r["account_type"] not in ("income", "income_other")
        )
        return {
            "result": {
                "income": str(income),
                "expense": str(expense),
                "net_profit": str(income - expense),
            },
            "accounts": accounts,
        }


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
        params: dict[str, Any] = {}
        where = ""
        if date:
            where += " AND m.date <= :date"
            params["date"] = date
        if company_id:
            where += " AND a.company_id = :company_id"
            params["company_id"] = company_id

        sql = f"""
            SELECT
                a.account_type,
                a.code,
                a.name,
                ROUND(SUM(ml.balance)::NUMERIC, 2) AS net_amount
            FROM account_move_line ml
            JOIN account_account a ON a.id = ml.account_id
            JOIN account_move m ON m.id = ml.move_id
            WHERE m.{_POSTED}
              AND ml.display_type NOT IN ('line_section','line_note')
              AND a.account_type NOT IN (
                  'income','income_other','expense','expense_other',
                  'expense_depreciation','expense_direct_cost','off_balance'
              )
              {where}
            GROUP BY a.id, a.code, a.name, a.account_type
            ORDER BY a.code
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text(sql), params)
            accounts = [dict(row._mapping) for row in rows]

        assets = sum(
            Decimal(str(r["net_amount"]))
            for r in accounts
            if r["account_type"].startswith("asset_")
        )
        liabilities = sum(
            Decimal(str(r["net_amount"]))
            for r in accounts
            if r["account_type"].startswith("liability_")
        )
        equity = sum(
            Decimal(str(r["net_amount"]))
            for r in accounts
            if r["account_type"].startswith("equity")
        )
        balanced = abs(assets - (liabilities + equity)) < Decimal("0.01")

        return {
            "result": {
                "assets": str(assets),
                "liabilities": str(liabilities),
                "equity": str(equity),
                "balanced": balanced,
            },
            "accounts": accounts,
        }


class AccountReportAgedReceivable(_VirtualReport):
    _abstract = False
    _name = "account.report.aged.receivable"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        date: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        return await _aged_report(env, "asset_receivable", date, company_id)


class AccountReportAgedPayable(_VirtualReport):
    _abstract = False
    _name = "account.report.aged.payable"

    @classmethod
    async def get_report(
        cls,
        env: Environment,
        date: str | datetime.date | None = None,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        return await _aged_report(env, "liability_payable", date, company_id)


async def _aged_report(
    env: Environment,
    account_type: str,
    date: str | datetime.date | None = None,
    company_id: int | None = None,
) -> dict[str, Any]:
    ref_date = date or datetime.date.today()
    params: dict[str, Any] = {"atype": account_type, "ref_date": ref_date}
    where_company = ""
    if company_id:
        where_company = " AND a.company_id = :company_id"
        params["company_id"] = company_id

    sql = f"""
        SELECT
            p.id AS partner_id,
            p.name AS partner_name,
            ROUND(ml.amount_residual::NUMERIC, 2) AS residual,
            m.invoice_date_due AS due_date,
            (CAST(:ref_date AS DATE) - m.invoice_date_due)::INTEGER AS days_overdue
        FROM account_move_line ml
        JOIN account_account a ON a.id = ml.account_id
        JOIN account_move m ON m.id = ml.move_id
        LEFT JOIN res_partner p ON p.id = ml.partner_id
        WHERE m.{_POSTED}
          AND ml.display_type = 'payment_term'
          AND a.account_type = :atype
          AND ml.amount_residual > 0
          {where_company}
        ORDER BY p.name, m.invoice_date_due
    """
    async with env.dml_conn() as conn:
        rows = await conn.execute(text(sql), params)
        lines = [dict(row._mapping) for row in rows]

    # Bucket by days overdue
    buckets = {
        "0_30": Decimal("0"),
        "31_60": Decimal("0"),
        "61_90": Decimal("0"),
        "90_plus": Decimal("0"),
    }
    for line in lines:
        days = line.get("days_overdue") or 0
        if days is None or days < 0:
            days = 0
        residual = Decimal(str(line["residual"]))
        if days <= 30:
            line["bucket"] = "0_30"
        elif days <= 60:
            line["bucket"] = "31_60"
        elif days <= 90:
            line["bucket"] = "61_90"
        else:
            line["bucket"] = "90_plus"
        buckets[line["bucket"]] += residual

    return {"result": lines, "buckets": {k: str(v) for k, v in buckets.items()}}
