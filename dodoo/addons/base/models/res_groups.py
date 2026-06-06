from dodoo.core.fields import Char
from dodoo.core.models import BaseModel


class ResGroups(BaseModel):
    _name = "res.groups"

    name = Char(size=128, required=True)
    full_name = Char(size=256)
    category = Char(size=128)
