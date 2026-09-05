from __future__ import annotations

from dodoo.core.fields import Char, Many2one, Selection
from dodoo.core.models import BaseModel

TAX_ROUNDING_CHOICES = [
    ("round_globally", "Round Globally"),
    ("round_per_line", "Round per Line"),
]


class ResCompany(BaseModel):
    _name = "res.company"

    name = Char(size=128, required=True)
    currency_id = Many2one("res.currency", required=True)
    partner_id = Many2one("res.partner")

    # Localization & Settings (005) — base-only references. The account-referencing
    # company columns (default_sale_tax_id / default_purchase_tax_id /
    # default_fiscal_position_id) are added by the localization addon as plain INTEGER
    # columns via DDL, mirroring account_data.py::_PARTNER_FK_COLUMNS, so `base` keeps
    # no dependency on `account`.
    lang = Char(size=16, default="ar")
    country_id = Many2one("res.country")
    tax_label = Char(size=16, default="VAT")
    tax_rounding_method = Selection(TAX_ROUNDING_CHOICES, default="round_globally")
