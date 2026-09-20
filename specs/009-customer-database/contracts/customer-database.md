# Contract: Customer Database (US1, US2, US3)

Covers FR-001…FR-014 (ADR-046/047/048).

## JSON-RPC (generic CRUD, via `execute_kw` on `res.partner`)

| Method | Args/kwargs | Returns | Notes |
|---|---|---|---|
| `create` | `{name, email?, phone?, street?, city?, state_id?, zip?, country_id?, vat?, property_payment_term_id?, property_currency_id?, customer_rank?}` | id | Validated against `CustomerCreate` at the HTTP boundary is **not** applicable here — generic `execute_kw` dispatch has no per-model Pydantic hook today, so `name`-required and email-format validation are enforced in `ResPartner.create`/`write` itself (a `classmethod` override, the same "override create/write, validate, call super()" pattern `AccountPaymentTermLine`/`AccountAccount` already use), not in `account/validators.py` (that file only backs dedicated `@route`s — see note below). `customer_rank` defaults to `1` when omitted and `name` is provided (a plain create is assumed to be a customer create from this feature's UI). |
| `write` | `{id: [...], vals: {...same fields...}}` | `True` | Same validation as `create`. |
| `search_read` | `domain=[["customer_rank", ">", 0], ...]`, `fields=[...]` | rows | Customer list/search (FR-003/004) — `customer-list.js` builds the domain client-side (`customer_rank > 0` plus, if `active` isn't requested, the model's existing default active-only filter); name/VAT substring matching is done client-side over the fetched page, following `coa-list.js`'s existing pattern. |
| `unlink` | `{ids: [...]}` | `True` / `400 DodooError` | FR-006: rejected if any id is referenced by `account_move.partner_id` or `account_payment.partner_id`. |

**Note on validation placement**: `CustomerCreate`/`CustomerUpdate` in `account/validators.py` are
used by a lightweight `POST /account/partner` / `PATCH /account/partner/{id}` convenience pair
(below) that `customer-form.js` actually calls instead of raw `execute_kw`, so the Pydantic
`extra="forbid"` whitelist boundary (SEC-001) is enforced before any DB write — the generic
`execute_kw` path is documented above for completeness (it's how every other model's CRUD already
works in this codebase) but the customer UI itself goes through the validated routes.

## REST routes

### `POST /account/partner`

Body: `CustomerCreate`. Creates a `res.partner` with `customer_rank=1`. Returns
`{"result": <partner_id>}`.

### `PATCH /account/partner/{partner_id}`

Body: `CustomerUpdate` (all fields optional). Returns `{"result": true}`.

### `GET /account/partner/{partner_id}/ar-ledger`

Read-only (ADR-047). Returns:

```json
{
  "balance": "1250.00",
  "currency_id": 1,
  "lines": [
    {"date": "2026-08-01", "type": "invoice", "move_id": 42, "reference": "INV/2026/0042", "amount": "1500.00", "status": "partial"},
    {"date": "2026-08-15", "type": "payment", "move_id": 7,  "reference": "PAY/2026/0007", "amount": "250.00",  "status": "open"}
  ]
}
```

`400 DodooError` if `partner_id` doesn't resolve to an existing partner. Excludes cancelled/voided
documents from `balance` (FR-012) but still lists them with `status: "cancelled"` (FR-009).

## Validation models (`account/validators.py`)

```text
class CustomerCreate(Payload):
    name: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    street: str | None = Field(default=None, max_length=256)
    city: str | None = Field(default=None, max_length=128)
    state_id: int | None = None
    zip: str | None = Field(default=None, max_length=32)
    country_id: int | None = None
    vat: str | None = Field(default=None, max_length=32)
    property_payment_term_id: int | None = None
    property_currency_id: int | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        # stdlib re, not EmailStr — no new dependency (Technical Context, research.md)
        if v and not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v

class CustomerUpdate(CustomerCreate):
    name: str | None = Field(default=None, min_length=1, max_length=256)  # optional on update
```

Both use `extra="forbid"` (SEC-001), matching every other validator already in this file.

## Behavior notes

- `ResPartner.create`/`write` (new classmethod overrides in `base/models/res_partner.py`) enforce
  `name` non-empty regardless of entry path (generic `execute_kw` or the dedicated routes above) —
  the one invariant that must hold no matter which path a caller uses.
- `customer-list.js`'s AR-balance column calls `get_ar_ledger` once per visible row/page rather than
  per keystroke; the search box only re-filters the already-fetched page client-side (no re-fetch of
  balances on every keystroke), keeping PERF-001's <1s target comfortable.
- Archiving is the existing generic `write(active=False)` — no dedicated route.
