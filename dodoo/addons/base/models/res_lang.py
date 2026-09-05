from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Selection
from dodoo.core.models import BaseModel

DIRECTION_CHOICES = [
    ("ltr", "Left-to-Right"),
    ("rtl", "Right-to-Left"),
]


class ResLang(BaseModel):
    _name = "res.lang"

    code = Char(size=16, required=True)
    name = Char(size=64, required=True)
    direction = Selection(DIRECTION_CHOICES, required=True)
    decimal_point = Char(size=4, default=".")
    thousands_sep = Char(size=4, default=",")
    grouping = Char(size=16, default="[3,0]")
    date_format = Char(size=32, default="%d/%m/%Y")
    active = Boolean(default=True)
