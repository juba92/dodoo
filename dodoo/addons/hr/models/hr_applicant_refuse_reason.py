"""``hr.applicant.refuse.reason`` — a reusable applicant rejection reason (FR-037). Global."""

from __future__ import annotations

from dodoo.core.fields import Char
from dodoo.core.models import BaseModel


class HrApplicantRefuseReason(BaseModel):
    _name = "hr.applicant.refuse.reason"

    name = Char(size=128, required=True)
