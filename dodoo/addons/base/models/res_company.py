from __future__ import annotations

from dodoo.core.fields import Char, Many2one
from dodoo.core.models import BaseModel


class ResCompany(BaseModel):
    _name = "res.company"

    name = Char(size=128, required=True)
    currency_id = Many2one("res.currency", required=True)
    partner_id = Many2one("res.partner")
