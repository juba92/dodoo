# Data Model: Customer Database

All fields use `dodoo.core.fields` types (`Char`, `Integer`, `Boolean`, `Many2one`, `Monetary`).
No new tables. New columns split by ownership per ADR-046: `base`-owned address fields are declared
`Field`s on `ResPartner`; `account`-owned fields are added via `account_data.py`'s existing
`_PARTNER_FK_COLUMNS` raw-`ALTER TABLE` idiom (`ADD COLUMN IF NOT EXISTS`), not declared `Field`s on
the `base`-owned class — exactly how `property_account_receivable_id`/`property_account_payable_id`/
`property_payment_term_id` already work today.

## Changed entity: `res.partner` (table `res_partner`)

### New columns — declared `Field`s on `base`'s `ResPartner` (same-owner addition)

| Field | Type | Notes |
|---|---|---|
| `street` | `Char(size=256)`, nullable | Billing address line. |
| `city` | `Char(size=128)`, nullable | |
| `state_id` | `Many2one("res.country.state")`, nullable | |
| `zip` | `Char(size=32)`, nullable | |
| `country_id` | `Many2one("res.country")`, nullable | |

### New columns — raw `ALTER TABLE`, owned by `account` (cross-addon idiom, ADR-046)

| Column | Type | Notes |
|---|---|---|
| `customer_rank` | `INTEGER DEFAULT 0` | **NEW.** `> 0` marks the partner as a customer (mirrors Odoo's `res.partner.customer_rank`). Set to `1` by the customer create/edit form; this feature does not auto-increment it on invoice posting (D3, research.md). |
| `property_currency_id` | `INTEGER` (FK `res_currency.id`), nullable | **NEW.** Per-customer default/override currency for invoicing and AR-ledger display. `NULL` → falls back to `res_company.currency_id`. |

### Existing columns, unused until now, now read/written by this feature

| Column | Type | Notes |
|---|---|---|
| `property_payment_term_id` | `INTEGER` (FK `account_payment_term.id`), nullable | Already added by `account_data.py`; previously dead. This feature's customer form reads/writes it; `NULL` → no forced default (D5, research.md — no company-level default term exists). |
| `property_account_receivable_id` | `INTEGER` (FK `account_account.id`), nullable | Already added and already read by `account_move.py`'s down-payment logic as an optional per-partner AR account override. Unchanged by this feature; the AR-ledger query (ADR-047) uses it the same way (falling back to the company's `asset_receivable`-type account when `NULL`). |

### Existing columns, unchanged, relevant to this feature

| Column | Type | Notes |
|---|---|---|
| `name` | `Char(size=256)`, required | Customer's legal/display name (FR-001). |
| `email` | `Char(size=256)`, nullable | Now format-validated at the Pydantic boundary (FR-013) — first field in this codebase to get real email-format validation; still a plain `Char`, no DB-level change. |
| `phone` | `Char(size=64)`, nullable | |
| `vat` | `Char(size=32)`, nullable | Tax/VAT number (FR-001). No uniqueness constraint (Edge Cases: duplicate VAT is a soft warning, not a DB constraint). |
| `active` | `Boolean(default=True)` | Existing archive flag; FR-005's "archive instead of delete" needs no new field. |

**New constraint**: `ResPartner.unlink` (new classmethod override, `base/models/res_partner.py`)
rejects deleting any partner id referenced by `account_move.partner_id` or
`account_payment.partner_id`, raising `DodooError` (FR-006). Archiving (`write(active=False)`)
remains unrestricted regardless of financial history (Edge Cases).

## Derived (non-stored) view: AR ledger

Not a table or model — a computed response shape returned by `ResPartner.get_ar_ledger(env,
partner_id)` (ADR-047), consumed by `GET /account/partner/{partner_id}/ar-ledger`:

```text
{
  "balance": "<Decimal string, in property_currency_id or company currency>",
  "currency_id": <int>,
  "lines": [
    {
      "date": "YYYY-MM-DD",
      "type": "invoice" | "credit_note" | "payment",
      "move_id": <int>,           # for drill-down navigation (FR-010)
      "reference": "<move name / payment reference>",
      "amount": "<Decimal string>",
      "status": "paid" | "partial" | "open" | "cancelled"
    },
    ...
  ]
}
```

Sourced from posted `account_move` rows (`move_type` in the existing `_SALE_TYPES`:
`out_invoice`/`out_refund`/`out_receipt`) whose lines hit an `asset_receivable`-type account, plus
`account_payment` rows, both filtered by `partner_id`; cancelled/voided documents appear with
`status: "cancelled"` and are excluded from `balance` (FR-012).

## Key Entities (from spec.md, restated with concrete field mapping)

- **Customer** → `res.partner` row with `customer_rank > 0`. Carries: `name`, `email`, `phone`,
  `street`/`city`/`state_id`/`zip`/`country_id` (billing address), `vat`,
  `property_payment_term_id`, `property_currency_id`, `active`.
- **Accounts Receivable Ledger (per customer)** → derived response from `get_ar_ledger`, not a
  stored entity (see above).
- **Payment Terms** → existing `account.payment.term` (`account_payment_term.py`), unchanged.
- **Currency** → existing `res.currency` (`res_currency.py`), unchanged.
