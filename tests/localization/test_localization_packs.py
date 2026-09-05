"""Unit tests for the Egypt localization package definition (no DB)."""
from __future__ import annotations

from dodoo.addons.localization.packs import PACKS, get_pack
from dodoo.addons.localization.packs.egypt import EGYPT_PACK


def test_registry_has_only_egypt():
    assert set(PACKS) == {"EG"}
    assert get_pack("EG") is EGYPT_PACK
    assert get_pack("eg") is EGYPT_PACK
    assert get_pack("GB") is None


def test_currency_is_egp():
    assert EGYPT_PACK["currency"]["code"] == "EGP"
    assert EGYPT_PACK["tax_label"] == "VAT"
    assert EGYPT_PACK["tax_rounding_method"] == "round_globally"


def test_four_taxes_with_correct_rates_and_use():
    taxes = {t["key"]: t for t in EGYPT_PACK["taxes"]}
    assert len(taxes) == 4
    assert taxes["eg_vat_14_sale"]["type_tax_use"] == "sale"
    assert taxes["eg_vat_14_sale"]["amount"] == "14"
    assert taxes["eg_vat_14_sale"]["tax_account_code"] == "2500"
    assert taxes["eg_vat_14_purch"]["type_tax_use"] == "purchase"
    assert taxes["eg_vat_14_purch"]["amount"] == "14"
    assert taxes["eg_vat_14_purch"]["tax_account_code"] == "2510"
    assert taxes["eg_vat_0_exempt"]["amount"] == "0"
    assert taxes["eg_vat_0_export"]["amount"] == "0"
    # exempt and export are distinct records even though both are 0%
    assert taxes["eg_vat_0_exempt"]["name"] != taxes["eg_vat_0_export"]["name"]


def test_fiscal_positions_domestic_and_export():
    fps = {f["name"]: f for f in EGYPT_PACK["fiscal_positions"]}
    assert set(fps) == {"Domestic", "Export"}
    assert fps["Domestic"]["tax_maps"] == []
    export_maps = {(m["src"], m["dest"]) for m in fps["Export"]["tax_maps"]}
    assert ("eg_vat_14_sale", "eg_vat_0_export") in export_maps
    assert ("eg_vat_14_purch", "eg_vat_0_export") in export_maps


def test_defaults_reference_the_14_percent_taxes():
    d = EGYPT_PACK["defaults"]
    assert d["default_sale_tax_key"] == "eg_vat_14_sale"
    assert d["default_purchase_tax_key"] == "eg_vat_14_purch"
    assert d["default_fiscal_position"] == "Domestic"
