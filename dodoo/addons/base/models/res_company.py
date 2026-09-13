from __future__ import annotations

from dodoo.core.fields import Char, Date, Integer, Many2one, Selection
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

    # 008-accounting-parity: fiscal lock dates (FR-031, ADR-039) and realized/
    # unrealized FX gain-loss accounts (FR-025, ADR-042). The columns are
    # added via account_data.py's ALTER TABLE idiom (research.md D5, so
    # `base` itself declares no dependency on `account`'s migration code),
    # but they must still be declared here as real fields — otherwise
    # BaseModel.write()/create() silently drop them (both filter `vals`
    # against `cls._fields`), making them permanently unwritable through the
    # ORM despite existing in the database.
    fiscalyear_lock_date = Date()
    tax_lock_date = Date()
    sale_lock_date = Date()
    purchase_lock_date = Date()
    income_currency_exchange_account_id = Many2one("account.account")
    expense_currency_exchange_account_id = Many2one("account.account")
    fiscalyear_last_month = Integer(default=12)
    fiscalyear_last_day = Integer(default=31)
