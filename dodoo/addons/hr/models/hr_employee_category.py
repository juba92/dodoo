"""``hr.employee.category`` — a free tag applied to employees (FR-004). Global (no company)."""

from __future__ import annotations

from dodoo.core.fields import Char, Integer
from dodoo.core.models import BaseModel


class HrEmployeeCategory(BaseModel):
    _name = "hr.employee.category"

    name = Char(size=64, required=True)
    color = Integer(default=0)
