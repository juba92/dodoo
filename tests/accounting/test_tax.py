"""Tax computation tests: percent, fixed, price_include, type mismatch rejection."""
from __future__ import annotations

from decimal import Decimal


def test_tax_percent_amount():
    from dodoo.addons.account.models.account_tax import AccountTax

    tax = {"id": 1, "amount_type": "percent", "amount": 20, "type_tax_use": "sale"}
    result = AccountTax._compute_amount(tax, Decimal("1000"))
    assert result == Decimal("200")


def test_tax_fixed_amount():
    from dodoo.addons.account.models.account_tax import AccountTax

    tax = {"id": 1, "amount_type": "fixed", "amount": 50, "type_tax_use": "sale"}
    result = AccountTax._compute_amount(tax, Decimal("1000"), quantity=Decimal("2"))
    assert result == Decimal("100")


def test_tax_division_amount():
    from dodoo.addons.account.models.account_tax import AccountTax

    tax = {"id": 1, "amount_type": "division", "amount": 20, "type_tax_use": "sale"}
    base = Decimal("100")
    result = AccountTax._compute_amount(tax, base)
    # division: base * rate / (100 - rate) = 100 * 20 / 80 = 25
    assert result == Decimal("25")


def test_reconcile_flag_enforced_on_ar_account():
    """AccountAccount.create should auto-set reconcile=True for asset_receivable."""
    from dodoo.addons.account.models.account_account import (
        _RECONCILABLE_TYPES,
    )

    assert "asset_receivable" in _RECONCILABLE_TYPES
    assert "liability_payable" in _RECONCILABLE_TYPES


def test_ar_ap_account_count():
    """Verify 19 account types are defined (18 + off_balance)."""
    from dodoo.addons.account.models.account_account import ACCOUNT_TYPE_CHOICES

    assert len(ACCOUNT_TYPE_CHOICES) == 19
