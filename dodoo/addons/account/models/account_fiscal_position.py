from __future__ import annotations

from dodoo.core.fields import Boolean, Char, Many2one
from dodoo.core.models import BaseModel


class AccountFiscalPosition(BaseModel):
    _name = "account.fiscal.position"

    name = Char(size=256, required=True)
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)


class AccountFiscalPositionTax(BaseModel):
    _name = "account.fiscal.position.tax"

    position_id = Many2one("account.fiscal.position", required=True)
    tax_src_id = Many2one("account.tax", required=True)
    tax_dest_id = Many2one("account.tax")


class AccountFiscalPositionAccount(BaseModel):
    _name = "account.fiscal.position.account"

    position_id = Many2one("account.fiscal.position", required=True)
    account_src_id = Many2one("account.account", required=True)
    account_dest_id = Many2one("account.account")
