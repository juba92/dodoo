from __future__ import annotations

from dodoo.core.fields import Char, Many2one
from dodoo.core.models import BaseModel


class ResCountryState(BaseModel):
    _name = "res.country.state"

    country_id = Many2one("res.country", required=True)
    code = Char(size=8, required=True)
    name = Char(size=128, required=True)
