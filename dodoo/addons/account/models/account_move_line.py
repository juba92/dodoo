from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import (
    Boolean,
    Char,
    Date,
    Float,
    Integer,
    Json,
    Many2many,
    Many2one,
    Monetary,
    Selection,
)
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

DISPLAY_TYPE_CHOICES = [
    ("product", "Product"),
    ("tax", "Tax"),
    ("payment_term", "Payment Term"),
    ("line_section", "Section"),
    ("line_note", "Note"),
    ("down_payment", "Down Payment"),
]

_SYSTEM_DISPLAY_TYPES = frozenset({"tax", "payment_term"})
_SECTION_NOTE = frozenset({"line_section", "line_note"})


class AccountMoveLine(BaseModel):
    _name = "account.move.line"

    move_id = Many2one("account.move", required=True)
    sequence = Integer(default=10)
    account_id = Many2one("account.account", required=True)
    partner_id = Many2one("res.partner")
    name = Char(size=256)
    date = Date(required=True)
    display_type = Selection(DISPLAY_TYPE_CHOICES, default="product")
    quantity = Float(default=1.0)
    price_unit = Monetary()
    discount = Monetary()
    price_subtotal = Monetary()
    price_total = Monetary()
    debit = Monetary()
    credit = Monetary()
    balance = Monetary()
    amount_currency = Monetary()
    currency_id = Many2one("res.currency")
    tax_base_amount = Monetary()
    analytic_distribution = Json()
    reconciled = Boolean(default=False)
    full_reconcile_id = Many2one("account.full.reconcile")
    amount_residual = Monetary()
    tax_line_id = Many2one("account.tax")
    tax_ids = Many2many(
        "account.tax",
        relation_table="account_move_line_tax_rel",
        column1="move_line_id",
        column2="tax_id",
    )

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        # Reject direct creation of system-generated line types (FR-019)
        dtype = vals.get("display_type", "product")
        if dtype in _SYSTEM_DISPLAY_TYPES:
            raise DodooError(
                f"display_type='{dtype}' lines are system-generated and cannot be created directly"
            )
        if vals.get("analytic_distribution"):
            await cls._validate_analytic_distribution(env, vals["analytic_distribution"])
        cls._apply_price_defaults(vals)
        return await super().create(env, vals)

    @classmethod
    async def write(cls, env: Environment, ids: list[int], vals: dict[str, Any]) -> bool:
        # FR-008, ADR-039: a posted (or cancelled) move's lines are immutable —
        # the same rejection shape AccountMove.write already raises for its
        # own header fields.
        if ids:
            from sqlalchemy import text

            async with env.dml_conn() as conn:
                rows = await conn.execute(
                    text(
                        "SELECT ml.id, m.state FROM account_move_line ml "
                        "JOIN account_move m ON m.id = ml.move_id "
                        "WHERE ml.id = ANY(:ids) AND m.state IN ('posted', 'cancel')"
                    ),
                    {"ids": ids},
                )
                locked = [r[0] for r in rows]
            if locked:
                raise DodooError(
                    f"Line(s) {locked} belong to a posted/cancelled move; cannot change. "
                    "Reset to draft first."
                )
        if vals.get("analytic_distribution"):
            await cls._validate_analytic_distribution(env, vals["analytic_distribution"])
        cls._apply_price_defaults(vals)
        return await super().write(env, ids, vals)

    @classmethod
    async def _validate_analytic_distribution(
        cls, env: Environment, distribution: dict[str, Any]
    ) -> None:
        """FR-038, ADR-045: every key must resolve to an active
        `analytic.account` id and the values must sum to 100 (±0.01)."""
        if not isinstance(distribution, dict) or not distribution:
            raise DodooError("analytic_distribution must be a non-empty object")

        try:
            account_ids = [int(k) for k in distribution]
        except (TypeError, ValueError) as exc:
            raise DodooError(
                "analytic_distribution keys must be analytic.account ids"
            ) from exc

        from sqlalchemy import text

        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id FROM analytic_account WHERE id = ANY(:ids) AND active = TRUE"
                ),
                {"ids": account_ids},
            )
            found = {r[0] for r in rows}

        missing = set(account_ids) - found
        if missing:
            raise DodooError(
                f"analytic_distribution references unknown or archived analytic.account "
                f"id(s): {sorted(missing)}"
            )

        total = sum(Decimal(str(v)) for v in distribution.values())
        if abs(total - Decimal("100")) > Decimal("0.01"):
            raise DodooError(
                f"analytic_distribution percentages must sum to 100 (got {total})"
            )

    @staticmethod
    def _apply_price_defaults(vals: dict[str, Any]) -> None:
        """Derive ``price_subtotal`` from ``price_unit`` × ``quantity`` net of any
        ``discount`` percentage (FR-010/013), when the caller supplies a unit price
        but not an explicit subtotal.

        ``price_total`` (subtotal + tax) is left to
        ``account.move.recompute_totals`` / ``action_post`` because it depends on
        the ``tax_ids`` Many2many, which is only linked after the row exists.
        """
        if "price_unit" not in vals:
            return
        if vals.get("quantity") in (None, ""):
            vals["quantity"] = 1.0
        if vals.get("price_subtotal") in (None, ""):
            qty = Decimal(str(vals.get("quantity") or 0))
            unit = Decimal(str(vals.get("price_unit") or 0))
            discount = Decimal(str(vals.get("discount") or 0))
            vals["price_subtotal"] = qty * unit * (Decimal("1") - discount / Decimal("100"))
