from __future__ import annotations

from dodoo.core.fields import Boolean, Char
from dodoo.core.models import BaseModel


class ResCountry(BaseModel):
    _name = "res.country"

    code = Char(size=2, required=True)
    name = Char(size=128, required=True)
    currency_code = Char(size=3, required=True)
    phone_code = Char(size=8)
    active = Boolean(default=True)
