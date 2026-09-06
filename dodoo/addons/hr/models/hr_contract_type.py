"""``hr.contract.type`` — seeded contract-type catalog. Nullable ``company_id`` (FR-064a)."""

from __future__ import annotations

from dodoo.core.fields import Char, Integer, Many2one
from dodoo.core.models import BaseModel


class HrContractType(BaseModel):
    _name = "hr.contract.type"

    name = Char(size=64, required=True)
    sequence = Integer(default=10)
    company_id = Many2one("res.company")
