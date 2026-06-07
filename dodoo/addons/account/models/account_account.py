from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

ACCOUNT_TYPE_CHOICES = [
    ("asset_receivable", "Receivable"),
    ("asset_cash", "Bank and Cash"),
    ("asset_current", "Current Assets"),
    ("asset_non_current", "Non-current Assets"),
    ("asset_prepayments", "Prepayments"),
    ("asset_fixed", "Fixed Assets"),
    ("liability_payable", "Payable"),
    ("liability_credit_card", "Credit Card"),
    ("liability_current", "Current Liabilities"),
    ("liability_non_current", "Non-current Liabilities"),
    ("equity", "Equity"),
    ("equity_unaffected", "Current Year Earnings"),
    ("income", "Income"),
    ("income_other", "Other Income"),
    ("expense", "Expenses"),
    ("expense_other", "Other Expenses"),
    ("expense_depreciation", "Depreciation"),
    ("expense_direct_cost", "Cost of Revenue"),
    ("off_balance", "Off Balance"),
]

_RECONCILABLE_TYPES = frozenset({"asset_receivable", "liability_payable"})


class AccountAccount(BaseModel):
    _name = "account.account"

    code = Char(size=64, required=True)
    name = Char(size=256, required=True)
    account_type = Selection(ACCOUNT_TYPE_CHOICES, required=True)
    reconcile = Boolean(default=False)
    currency_id = Many2one("res.currency")
    active = Boolean(default=True)
    company_id = Many2one("res.company", required=True)

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        # Auto-enforce reconcile=True for AR/AP accounts
        if vals.get("account_type") in _RECONCILABLE_TYPES:
            vals = {**vals, "reconcile": True}
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        # Prevent disabling reconcile on AR/AP accounts
        if "reconcile" in vals and not vals["reconcile"]:
            for acct_id in ids:
                records = await super().read(env, [acct_id], ["account_type"])
                if records and records[0].get("account_type") in _RECONCILABLE_TYPES:
                    raise DodooError(
                        f"Account {acct_id} is a receivable/payable account; "
                        "reconcile=True cannot be disabled"
                    )
        # Propagate reconcile=True if account_type changes to AR/AP
        if vals.get("account_type") in _RECONCILABLE_TYPES:
            vals = {**vals, "reconcile": True}
        return await super().write(env, ids, vals)

    @classmethod
    async def get_balance(cls, env: Environment, account_id: int) -> dict[str, str]:
        """Return {debit, credit, net} sum of all posted lines on this account."""
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT "
                    "  ROUND(SUM(debit)::NUMERIC, 2)   AS total_debit, "
                    "  ROUND(SUM(credit)::NUMERIC, 2)  AS total_credit, "
                    "  ROUND(SUM(balance)::NUMERIC, 2) AS net_balance "
                    "FROM account_move_line ml "
                    "JOIN account_move m ON m.id = ml.move_id "
                    "WHERE ml.account_id = :acct AND m.state = 'posted' "
                    "  AND ml.display_type NOT IN ('line_section','line_note')"
                ),
                {"acct": account_id},
            )
            r = row.fetchone()
        return {
            "debit": str(r[0] or Decimal("0")),
            "credit": str(r[1] or Decimal("0")),
            "net": str(r[2] or Decimal("0")),
        }


class AccountAccountGroup(BaseModel):
    _name = "account.account.group"

    name = Char(size=256, required=True)
    code_prefix_start = Char(size=64)
    code_prefix_end = Char(size=64)
    parent_id = Many2one("account.account.group")
    company_id = Many2one("res.company", required=True)
