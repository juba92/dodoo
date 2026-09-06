"""``hr.leave.type`` — configuration for a category of time off (FR-020). Nullable company_id."""

from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Integer, Many2one, Selection
from dodoo.core.models import BaseModel

REQUEST_UNIT = [("day", "Day"), ("hour", "Hour")]
APPROVAL_MODE = [
    ("no_validation", "No Validation"),
    ("manager", "Manager"),
    ("hr", "HR Officer"),
    ("both", "Manager then Second Approval"),
]


class HrLeaveType(BaseModel):
    _name = "hr.leave.type"

    name = Char(size=64, required=True)
    company_id = Many2one("res.company")
    request_unit = Selection(REQUEST_UNIT, default="day")
    is_paid = Boolean(default=True)
    allocation_required = Boolean(default=True)
    allow_negative = Boolean(default=False)
    approval_mode = Selection(APPROVAL_MODE, default="manager")
    color = Integer(default=0)
