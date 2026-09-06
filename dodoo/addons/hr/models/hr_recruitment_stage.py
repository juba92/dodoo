"""``hr.recruitment.stage`` — a sequenced pipeline column (FR-033). Nullable company_id."""

from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Integer, Many2one
from dodoo.core.models import BaseModel


class HrRecruitmentStage(BaseModel):
    _name = "hr.recruitment.stage"

    name = Char(size=64, required=True)
    sequence = Integer(default=10)
    is_hired_stage = Boolean(default=False)
    fold = Boolean(default=False)
    company_id = Many2one("res.company")
