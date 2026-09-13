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

# FR-002, ADR-037: these types can never be reconcilable — off-balance accounts
# don't participate in AR/AP-style matching, and cash/credit-card accounts are
# cleared by bank reconciliation, not open-item reconciliation.
_NEVER_RECONCILABLE_TYPES = frozenset(
    {"off_balance", "asset_cash", "liability_credit_card"}
)


def _group_sort_key(code: str) -> tuple[int, str]:
    """Numeric-string comparison per ADR-037: an all-digit code compares as an
    integer (so "9000" > "800"); a non-numeric code falls back to plain string
    comparison, sorted after every numeric one."""
    return (0, f"{int(code):020d}") if code.isdigit() else (1, code)


class AccountAccount(BaseModel):
    _name = "account.account"

    code = Char(size=64, required=True)
    name = Char(size=256, required=True)
    account_type = Selection(ACCOUNT_TYPE_CHOICES, required=True)
    reconcile = Boolean(default=False)
    group_id = Many2one("account.account.group")
    currency_id = Many2one("res.currency")
    active = Boolean(default=True)
    company_id = Many2one("res.company", required=True)

    @classmethod
    async def _resolve_group_id(
        cls, env: Environment, code: str, company_id: int
    ) -> int | None:
        """FR-001: find the `account.account.group` whose
        `code_prefix_start <= code <= code_prefix_end` (numeric-string
        comparison), matching Odoo's own `_compute_account_group`."""
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, code_prefix_start, code_prefix_end FROM account_account_group "
                    "WHERE company_id = :cid "
                    "AND code_prefix_start IS NOT NULL AND code_prefix_end IS NOT NULL"
                ),
                {"cid": company_id},
            )
            candidates = [dict(r._mapping) for r in rows]

        code_key = _group_sort_key(code)
        for candidate in candidates:
            start_key = _group_sort_key(candidate["code_prefix_start"])
            end_key = _group_sort_key(candidate["code_prefix_end"])
            if start_key <= code_key <= end_key:
                return candidate["id"]
        return None

    @classmethod
    def _enforce_reconcile_constraints(cls, account_type: str | None, vals: dict[str, Any]) -> dict[str, Any]:
        if account_type in _RECONCILABLE_TYPES:
            return {**vals, "reconcile": True}
        if account_type in _NEVER_RECONCILABLE_TYPES:
            if vals.get("reconcile"):
                raise DodooError(
                    f"account_type '{account_type}' cannot be reconcilable (FR-002)"
                )
            return {**vals, "reconcile": False}
        return vals

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        vals = cls._enforce_reconcile_constraints(vals.get("account_type"), vals)
        # group_id is server-resolved only — never accepted as client input (FR-001).
        vals = {k: v for k, v in vals.items() if k != "group_id"}
        record_id = await super().create(env, vals)
        if vals.get("code") and vals.get("company_id"):
            group_id = await cls._resolve_group_id(env, vals["code"], vals["company_id"])
            if group_id is not None:
                await super().write(env, [record_id], {"group_id": group_id})
        return record_id

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        vals = {k: v for k, v in vals.items() if k != "group_id"}

        if "account_type" in vals or "reconcile" in vals:
            for acct_id in ids:
                records = await super().read(env, [acct_id], ["account_type"])
                if not records:
                    continue
                effective_type = vals.get("account_type", records[0].get("account_type"))
                # Prevent disabling reconcile on AR/AP accounts.
                if (
                    "reconcile" in vals
                    and not vals["reconcile"]
                    and effective_type in _RECONCILABLE_TYPES
                ):
                    raise DodooError(
                        f"Account {acct_id} is a receivable/payable account; "
                        "reconcile=True cannot be disabled"
                    )
                if (
                    vals.get("reconcile")
                    and effective_type in _NEVER_RECONCILABLE_TYPES
                ):
                    raise DodooError(
                        f"account_type '{effective_type}' cannot be reconcilable (FR-002)"
                    )
            vals = cls._enforce_reconcile_constraints(vals.get("account_type"), vals)

        result = await super().write(env, ids, vals)

        if "code" in vals:
            for acct_id in ids:
                records = await super().read(env, [acct_id], ["code", "company_id"])
                if not records or not records[0].get("code"):
                    continue
                group_id = await cls._resolve_group_id(
                    env, records[0]["code"], records[0]["company_id"]
                )
                await super().write(env, [acct_id], {"group_id": group_id})

        return result

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
