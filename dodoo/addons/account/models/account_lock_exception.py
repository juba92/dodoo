from __future__ import annotations

from dodoo.core.fields import Boolean, Date, Many2one, Selection
from dodoo.core.models import BaseModel

LOCK_DATE_FIELD_CHOICES = [
    ("fiscalyear_lock_date", "Fiscal Year Lock"),
    ("tax_lock_date", "Tax Return Lock"),
    ("sale_lock_date", "Sales Lock"),
    ("purchase_lock_date", "Purchase Lock"),
]


class AccountLockException(BaseModel):
    """A time-boxed, scoped relaxation of one of `res_company`'s four lock
    dates for a specific user and/or journal (FR-033, ADR-039)."""

    _name = "account.lock.exception"

    company_id = Many2one("res.company", required=True)
    lock_date_field = Selection(LOCK_DATE_FIELD_CHOICES, required=True)
    lock_date = Date(required=True)
    user_id = Many2one("res.users")
    journal_id = Many2one("account.journal")
    end_date = Date(required=True)
    granted_by_id = Many2one("res.users", required=True)
    active = Boolean(default=True)
