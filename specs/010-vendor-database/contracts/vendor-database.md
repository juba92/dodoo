# Contract: Vendor Database (US1, US2, US3)

Covers FR-001…FR-015 (ADR-049/050/051). Mirrors `specs/009-customer-database/contracts/customer-database.md`
file-for-file, substituting the vendor/AP terms throughout.

## JSON-RPC (generic CRUD, via `execute_kw` on `res.partner`)

| Method | Args/kwargs | Returns | Notes |
|---|---|---|---|
| `create` | `{name, email?, phone?, street?, city?, state_id?, zip?, country_id?, vat?, property_supplier_payment_term_id?, property_currency_id?, supplier_rank?}` | id | `name`-required and email-format validation are enforced in `ResPartner.create`/`write` itself (unchanged from 009 — no new override needed, since `name` validation is already generic across every partner, not customer-specific). `supplier_rank` defaults to `1` when omitted and `name` is provided (a plain create via the dedicated vendor routes is assumed to be a vendor create). |
| `write` | `{id: [...], vals: {...same fields...}}` | `True` | Same validation as `create`. |
| `search_read` | n/a for the vendor list | — | `supplier_rank` is a raw, undeclared column (ADR-049), so `compile_domain` rejects `[["supplier_rank", ">", 0]]` — the generic RPC cannot filter on it. `vendor-list.js` uses `GET /account/vendors` instead (below); name/VAT substring matching is done client-side over the fetched page, following `customer-list.js`'s existing pattern. |
| `unlink` | `{ids: [...]}` | `True` / `400 DodooError` | FR-006: rejected if any id is referenced by `account_move.partner_id` or `account_payment.partner_id` — the existing 009 guard, unchanged (research.md D7). |

**Note on validation placement**: `VendorCreate`/`VendorUpdate` in `account/validators.py` back a
lightweight `POST /account/vendor` / `PATCH /account/vendor/{id}` convenience pair (below) that
`vendor-form.js` actually calls. **Not** `POST`/`PATCH /account/partner`: those paths already
dispatch to 009's `create_customer`/`update_customer` handlers, fixed to the `CustomerCreate`/
`CustomerUpdate` validators (`extra="forbid"` — a vendor-shaped payload with
`property_supplier_payment_term_id`/`supplier_rank` would be rejected by them); a single route
cannot carry two different handlers, so vendor create/update get their own path, distinct from but
parallel to the customer one (Behavior notes).

## REST routes

### `GET /account/vendors`

Read-only. Query param `include_archived=true` to include archived vendors (default: active only).
Returns `{"result": [{id, name, vat, email, phone, active, supplier_rank}, ...]}`, ordered by name
— the raw route `vendor-list.js` uses in place of the generic `search_read` (see correction above),
mirroring `GET /account/customers`.

### `POST /account/vendor`

Body: `VendorCreate`. Creates a `res.partner` with `supplier_rank=1`. Returns
`{"result": <partner_id>}`.

### `GET /account/partner/{partner_id}`

Read-only. **Shared, unchanged route** — 009's existing generic partner read already returns every
raw, undeclared column relevant to either role (`customer_rank`, `property_currency_id`,
`property_payment_term_id`) and needs one addition: `supplier_rank` and
`property_supplier_payment_term_id` added to its `SELECT` column list (ADR-049) so a vendor's
raw-owned fields come back too. `vendor-form.js` uses this same route to load a vendor for editing,
identical to how `customer-form.js` already uses it.

### `PATCH /account/vendor/{partner_id}`

Body: `VendorUpdate` (all fields optional). Returns `{"result": true}`. A distinct path from
customer's `PATCH /account/partner/{id}` for the same reason as `POST /account/vendor` above.

### `GET /account/partner/{partner_id}/ap-ledger`

Read-only (ADR-050). Returns:

```json
{
  "balance": "875.00",
  "currency_id": 1,
  "lines": [
    {"date": "2026-08-03", "type": "bill", "move_id": 51, "reference": "BILL/2026/0051", "amount": "1000.00", "status": "partial"},
    {"date": "2026-08-20", "type": "payment", "move_id": 12, "reference": "PAY/2026/0012", "amount": "125.00", "status": "open"}
  ]
}
```

`400 DodooError` if `partner_id` doesn't resolve to an existing partner. Excludes cancelled/voided
documents from `balance` (FR-012) but still lists them with `status: "cancelled"` (FR-009).

## Validation models (`account/validators.py`)

```text
class VendorCreate(Payload):
    name: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    street: str | None = Field(default=None, max_length=256)
    city: str | None = Field(default=None, max_length=128)
    state_id: int | None = None
    zip: str | None = Field(default=None, max_length=32)
    country_id: int | None = None
    vat: str | None = Field(default=None, max_length=32)
    property_supplier_payment_term_id: int | None = None
    property_currency_id: int | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        # Reuses the same _EMAIL_RE stdlib pattern CustomerCreate already defines
        # in this file — no duplicate regex, no new dependency.
        if v and not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v

class VendorUpdate(VendorCreate):
    name: str | None = Field(default=None, min_length=1, max_length=256)  # optional on update
```

Both use `extra="forbid"` (SEC-001), matching `CustomerCreate`/`CustomerUpdate` and every other
validator already in this file.

## Behavior notes

- `create_vendor`/`update_vendor` HTTP handlers follow `create_customer`/`update_customer`'s exact
  shape (`http/__init__.py`): validate → `ResPartner.create`/`write` for declared fields →
  `write_partner_properties` for the raw `account`-owned columns (`supplier_rank`,
  `property_supplier_payment_term_id`, `property_currency_id`) — `write_partner_properties`'s
  `_PROPERTY_COLUMNS` tuple gains `supplier_rank` and `property_supplier_payment_term_id`
  alongside its existing three entries.
- A partner already flagged as a customer (`customer_rank > 0`) that is then edited to also be a
  vendor goes through `PATCH /account/vendor/{id}` with `supplier_rank: 1` — the same partner row
  is updated in place, not re-created (Edge Cases: dual customer/vendor role, FR-015). Promoting an
  existing vendor to also be a customer works the same way in reverse via 009's
  `PATCH /account/partner/{id}`.
- `vendor-list.js`'s AP-balance column calls `get_ap_ledger` once per visible row/page rather than
  per keystroke, identical to `customer-list.js`'s AR-balance column (PERF-001).
- Archiving is the existing generic `write(active=False)` — no dedicated route, same as customers.
