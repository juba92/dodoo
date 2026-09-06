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
        cls._apply_price_defaults(vals)
        return await super().create(env, vals)

    @classmethod
    async def write(cls, env: Environment, ids: list[int], vals: dict[str, Any]) -> bool:
        cls._apply_price_defaults(vals)
        return await super().write(env, ids, vals)

    @staticmethod
    def _apply_price_defaults(vals: dict[str, Any]) -> None:
        """Derive ``price_subtotal`` from ``price_unit`` × ``quantity`` when the
        caller supplies a unit price but not an explicit subtotal.

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
            vals["price_subtotal"] = qty * unit
