from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Many2one
from dodoo.core.models import BaseModel


class ResPartner(BaseModel):
    _name = "res.partner"

    name = Char(size=256, required=True)
    company_id = Many2one("res.company")
    email = Char(size=256)
    phone = Char(size=64)
    vat = Char(size=32)
    active = Boolean(default=True)
    is_company = Boolean(default=False)
