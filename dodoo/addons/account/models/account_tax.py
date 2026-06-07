from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from dodoo.core.fields import (
    Boolean,
    Char,
    Integer,
    Many2many,
    Many2one,
    Monetary,
    Selection,
)
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    pass

TAX_USE_CHOICES = [
    ("sale", "Sales"),
    ("purchase", "Purchase"),
    ("none", "None"),
]

AMOUNT_TYPE_CHOICES = [
    ("percent", "Percent"),
    ("fixed", "Fixed"),
    ("division", "Division"),
    ("group", "Group"),
]

REPARTITION_TYPE_CHOICES = [
    ("base", "Base"),
    ("tax", "Tax"),
]

DOCUMENT_TYPE_CHOICES = [
    ("invoice", "Invoice"),
    ("refund", "Refund"),
]


class AccountTaxGroup(BaseModel):
    _name = "account.tax.group"

    name = Char(size=256, required=True)
    sequence = Integer(default=10)
    company_id = Many2one("res.company", required=True)


class AccountTax(BaseModel):
    _name = "account.tax"

    name = Char(size=256, required=True)
    type_tax_use = Selection(TAX_USE_CHOICES, required=True)
    amount_type = Selection(AMOUNT_TYPE_CHOICES, required=True)
    amount = Monetary()
    price_include = Boolean(default=False)
    include_base_amount = Boolean(default=False)
    tax_group_id = Many2one("account.tax.group")
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)
    children_tax_ids = Many2many(
        "account.tax",
        relation_table="account_tax_filiation_rel",
        column1="parent_id",
        column2="child_id",
    )

    @classmethod
    def _compute_amount(
        cls,
        tax: dict[str, Any],
        base: Decimal,
        quantity: Decimal = Decimal("1"),
    ) -> Decimal:
        """Compute raw (unrounded) tax amount for a single tax on a given base."""
        amount_type = tax.get("amount_type", "percent")
        amount = Decimal(str(tax.get("amount", 0)))

        if amount_type == "percent":
            return base * amount / Decimal("100")
        if amount_type == "fixed":
            return amount * quantity
        if amount_type == "division":
            denom = Decimal("100") - amount
            if denom == 0:
                return Decimal("0")
            return base * amount / denom
        return Decimal("0")  # group type handled at engine level


class AccountTaxRepartitionLine(BaseModel):
    _name = "account.tax.repartition.line"

    tax_id = Many2one("account.tax", required=True)
    document_type = Selection(DOCUMENT_TYPE_CHOICES, required=True)
    repartition_type = Selection(REPARTITION_TYPE_CHOICES, required=True)
    factor_percent = Monetary()
    account_id = Many2one("account.account")
    sequence = Integer(default=10)
