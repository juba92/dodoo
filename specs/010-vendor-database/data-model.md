# Data Model: Vendor Database

All fields use `dodoo.core.fields` types. No new tables, no new `base`-owned columns (009 already
added the billing-address fields this feature reuses). One new column, added via
`account_data.py`'s existing `_PARTNER_FK_COLUMNS` raw-`ALTER TABLE` idiom (ADR-049) — exactly how
`customer_rank` was added in 009.

## Changed entity: `res.partner` (table `res_partner`)

### New column — raw `ALTER TABLE`, owned by `account` (cross-addon idiom, ADR-049)

| Column | Type | Notes |
|---|---|---|
| `supplier_rank` | `INTEGER DEFAULT 0` | **NEW.** `> 0` marks the partner as a vendor (mirrors Odoo's `res.partner.supplier_rank`). Set to `1` by the vendor create/edit form; independent of `customer_rank` — a partner may carry either, both, or neither (FR-015). |

### Existing columns, unused until now, now read/written by this feature

| Column | Type | Notes |
|---|---|---|
| `property_supplier_payment_term_id` | `INTEGER` (FK `account_payment_term.id`), nullable | Already added by `account_data.py` (pre-existing, prior cycle); previously dead. This feature's vendor form reads/writes it as the vendor's default payment term — kept as a separate column from `property_payment_term_id` (the customer-side default) since a partner that is both a customer and a vendor may reasonably have different default terms for each role, mirroring Odoo's own separate `property_payment_term_id`/`property_supplier_payment_term_id` fields. |
| `property_account_payable_id` | `INTEGER` (FK `account_account.id`), nullable | Already added and already *read* by `account_payment.py`'s vendor-payment posting logic as an optional per-partner AP account override. This feature's vendor form is the first place that *writes* it (optional override; `NULL` falls back to the company's `liability_payable`-type account, unchanged behavior). |

### Existing columns, unchanged, reused as-is from 009-customer-database

| Column | Type | Notes |
|---|---|---|
| `name` | `Char(size=256)`, required | Vendor's legal/display name (FR-001). |
| `email` | `Char(size=256)`, nullable | Same Pydantic email-format validation as the customer form (FR-013), reusing `VendorCreate`'s own `field_validator`. |
| `phone` | `Char(size=64)`, nullable | |
| `street` / `city` / `state_id` / `zip` / `country_id` | (see 009 data-model.md) | Billing address — added by 009, shared by both customer and vendor roles on the same partner row. |
| `vat` | `Char(size=32)`, nullable | Tax/VAT number (FR-001). No uniqueness constraint (Edge Cases: duplicate VAT is a soft warning). |
| `property_currency_id` | `INTEGER` (FK `res_currency.id`), nullable | Added by 009 as the customer-side default currency override; reused unchanged as the vendor's default/override currency too (one currency preference per partner row, not per role — matches Odoo's single `property_purchase_currency_id`-less design where `res.partner` has one general currency field shared across both AR and AP use). `NULL` → falls back to `res_company.currency_id`. |
| `active` | `Boolean(default=True)` | Existing archive flag; FR-005 needs no new field. |

**Existing constraint, unchanged**: `ResPartner.unlink` (009's `base/models/res_partner.py`
classmethod override) already rejects deleting any partner id referenced by
`account_move.partner_id` or `account_payment.partner_id`, with no `move_type`/`partner_type`
filter — already covers vendor bills/payments with zero changes (research.md D7).

## Derived (non-stored) view: AP ledger

Not a table or model — a computed response shape returned by `get_ap_ledger(env, partner_id)`, a
new module-level function in `account/models/account_partner.py` (ADR-050, alongside the existing
`get_ar_ledger`), consumed by `GET /account/partner/{partner_id}/ap-ledger`:

```text
{
  "balance": "<Decimal string, in property_currency_id or company currency>",
  "currency_id": <int>,
  "lines": [
    {
      "date": "YYYY-MM-DD",
      "type": "bill" | "credit_note" | "payment",
      "move_id": <int>,           # for drill-down navigation (FR-010)
      "reference": "<move name / payment reference>",
      "amount": "<Decimal string>",
      "status": "paid" | "partial" | "open" | "cancelled"
    },
    ...
  ]
}
```

Sourced from posted `account_move` rows (`move_type` in the existing `_PURCHASE_TYPES`:
`in_invoice`/`in_refund`/`in_receipt`) whose lines hit a `liability_payable`-type account, plus
`account_payment` rows with `partner_type = 'supplier'`, both filtered by `partner_id`;
cancelled/voided documents appear with `status: "cancelled"` and are excluded from `balance`
(FR-012) — same shape as `get_ar_ledger`, reusing the same `_status_and_balance` pure helper
(research.md D5).

## Key Entities (from spec.md, restated with concrete field mapping)

- **Vendor** → `res.partner` row with `supplier_rank > 0`. Carries: `name`, `email`, `phone`,
  `street`/`city`/`state_id`/`zip`/`country_id` (billing address, shared with the customer role),
  `vat`, `property_supplier_payment_term_id`, `property_currency_id`, `active`.
- **Accounts Payable Ledger (per vendor)** → derived response from `get_ap_ledger`, not a stored
  entity (see above).
- **Payment Terms** → existing `account.payment.term` (`account_payment_term.py`), unchanged.
- **Currency** → existing `res.currency` (`res_currency.py`), unchanged.
