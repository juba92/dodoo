from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import (
    Boolean,
    Char,
    Date,
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
        return await super().create(env, vals)
