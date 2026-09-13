from __future__ import annotations

from dodoo.core.fields import Char, Many2one
from dodoo.core.models import BaseModel


class AnalyticPlan(BaseModel):
    _name = "analytic.plan"

    name = Char(size=128, required=True)
    parent_id = Many2one("analytic.plan")
    company_id = Many2one("res.company", required=True)
