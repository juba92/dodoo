from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Many2one
from dodoo.core.models import BaseModel


class AnalyticAccount(BaseModel):
    _name = "analytic.account"

    name = Char(size=128, required=True)
    code = Char(size=32)
    plan_id = Many2one("analytic.plan")
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)
