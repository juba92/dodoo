from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Many2one, Selection
from dodoo.core.models import BaseModel

JOURNAL_TYPE_CHOICES = [
    ("sale", "Sales"),
    ("purchase", "Purchase"),
    ("cash", "Cash"),
    ("bank", "Bank"),
    ("general", "Miscellaneous"),
]


class AccountJournal(BaseModel):
    _name = "account.journal"

    name = Char(size=256, required=True)
    code = Char(size=10, required=True)
    type = Selection(JOURNAL_TYPE_CHOICES, required=True)
    default_account_id = Many2one("account.account")
    suspense_account_id = Many2one("account.account")
    currency_id = Many2one("res.currency")
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)
