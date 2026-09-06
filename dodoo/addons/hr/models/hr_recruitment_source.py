"""``hr.recruitment.source`` — where an applicant came from (FR-034). Nullable company_id."""

from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Many2one
from dodoo.core.models import BaseModel


class HrRecruitmentSource(BaseModel):
    _name = "hr.recruitment.source"

    name = Char(size=64, required=True)
    is_referral = Boolean(default=False)
    company_id = Many2one("res.company")
