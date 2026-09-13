from __future__ import annotations

from dodoo.core.fields import Char, Many2one, Monetary, Selection
from dodoo.core.models import BaseModel

CASH_ROUNDING_METHOD_CHOICES = [
    ("up", "Up"),
    ("down", "Down"),
    ("half_up", "Half-Up"),
]

CASH_ROUNDING_STRATEGY_CHOICES = [
    ("add_invoice_line", "Add a Rounding Line"),
    ("biggest_tax", "Adjust the Biggest Tax"),
]


class AccountCashRounding(BaseModel):
    """A configurable cash-rounding profile (FR-030, ADR-043)."""

    _name = "account.cash.rounding"

    name = Char(size=128, required=True)
    rounding = Monetary(required=True)
    rounding_method = Selection(CASH_ROUNDING_METHOD_CHOICES, default="half_up")
    strategy = Selection(CASH_ROUNDING_STRATEGY_CHOICES, default="add_invoice_line")
    account_id = Many2one("account.account")
    company_id = Many2one("res.company", required=True)
