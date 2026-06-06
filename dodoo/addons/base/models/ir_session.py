from dodoo.core.fields import Char, Datetime, Many2one
from dodoo.core.models import BaseModel


class IrSession(BaseModel):
    _name = "ir.session"

    token = Char(size=64, required=True)
    user_id = Many2one("res.users", required=True)
    expire_date = Datetime(required=True)
