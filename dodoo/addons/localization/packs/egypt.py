"""Egypt localization package (l10n_eg equivalent).

Explicit, spec-defined contents (FR-034..FR-037): EGP currency, VAT 14% sale + purchase
mapped to the VAT-collected / VAT-deductible accounts, a 0% exempt tax, a 0% zero-rated
export tax, Domestic + Export fiscal positions (Export substitutes the 14% taxes with the
0% export tax), the "VAT" document label, and round-globally rounding.
"""

from __future__ import annotations

EGYPT_PACK: dict = {
    "country_code": "EG",
    "currency": {
        "code": "EGP",
        "name": "Egyptian Pound",
        "symbol": "£",  # £E
        "rounding": 2,
    },
    "tax_label": "VAT",
    "tax_rounding_method": "round_globally",
    "tax_group": "VAT",
    # key: stable identifier used for fiscal-position mapping + defaults
    "taxes": [
        {
            "key": "eg_vat_14_sale",
            "name": "VAT 14%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": "14",
            "tax_account_code": "2500",  # VAT Collected
        },
        {
            "key": "eg_vat_14_purch",
            "name": "VAT 14% (Purchase)",
            "type_tax_use": "purchase",
            "amount_type": "percent",
            "amount": "14",
            "tax_account_code": "2510",  # VAT Deductible
        },
        {
            "key": "eg_vat_0_exempt",
            "name": "VAT 0% (Exempt)",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": "0",
            "tax_account_code": None,
        },
        {
            "key": "eg_vat_0_export",
            "name": "VAT 0% (Export)",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": "0",
            "tax_account_code": None,
        },
    ],
    "fiscal_positions": [
        {"name": "Domestic", "tax_maps": []},
        {
            "name": "Export",
            "tax_maps": [
                {"src": "eg_vat_14_sale", "dest": "eg_vat_0_export"},
                {"src": "eg_vat_14_purch", "dest": "eg_vat_0_export"},
            ],
        },
    ],
    "defaults": {
        "default_sale_tax_key": "eg_vat_14_sale",
        "default_purchase_tax_key": "eg_vat_14_purch",
        "default_fiscal_position": "Domestic",
    },
    # Generic account-addon demo taxes to archive on a fresh Egyptian install
    # (retained, never deleted — FR-030 / research R7).
    "supersedes_tax_names": ["Tax 20.00%", "Tax 20.00% (Purchase)"],
}
