from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Integer
from dodoo.core.models import BaseModel


class ResCurrency(BaseModel):
    _name = "res.currency"

    code = Char(size=3, required=True)
    name = Char(size=64)
    symbol = Char(size=8)
    rounding = Integer(default=2)
    active = Boolean(default=True)
