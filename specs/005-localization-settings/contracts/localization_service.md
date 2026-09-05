# Contract: `localization.service.apply_country_localization`

Internal Python service (not directly HTTP-exposed). Called by
`res.config.settings.set_values` and by `seed_localization_data` on fresh install. Documented as a contract
because its return shape is what `set_values` forwards to the SPA.

## Signature

```python
async def apply_country_localization(
    env: Environment,
    company_id: int,
    country_code: str,
    *,
    confirm_currency_change: bool = False,
) -> dict
```

## Preconditions

- `country_code` is an active `res_country.code` (caller validates; service re-asserts).
- Caller has already performed the Administrator check (`set_values` / seed context).
- The `account` addon is installed (chart of accounts + `2500` / `2510` accounts exist for the company).

## Outcomes

### 1. Neutral country (no `PACKS` entry, e.g. `GB`)

Writes only `res_company.country_id`. Returns:

```json
{ "applied": false, "country": "GB" }
```

No tax / currency / fiscal-position / default changes (FR-017).

### 2. Currency conflict — blocked

Target currency ≠ current `res_company.currency_id`, **and** `COUNT(account_move_line ⋈ account_move
WHERE state='posted') > 0`, **and** `confirm_currency_change is False`:

```json
{
  "applied": false,
  "warning": "currency_change_requires_confirmation",
  "from": "EUR",
  "to": "EGP",
  "posted_lines": 128
}
```

**No writes at all** — `country_id` is not changed either (FR-028). Caller re-invokes with
`confirm_currency_change=True` to proceed.

### 3. Applied (fresh, confirmed, or no currency change)

Idempotent seeding into existing `account` / `base` models (see data-model.md). Returns:

```json
{
  "applied": true,
  "country": "EG",
  "currency": "EGP",
  "currency_seeded": true,
  "taxes_created": 4,
  "taxes_reused": 0,
  "fiscal_positions_created": 2,
  "fiscal_positions_reused": 0,
  "archived_generic_taxes": 2,
  "company_defaults": {
    "currency_id": 5,
    "tax_label": "VAT",
    "tax_rounding_method": "round_globally",
    "default_sale_tax_id": 11,
    "default_purchase_tax_id": 12,
    "default_fiscal_position_id": 4
  }
}
```

## Invariants (asserted by tests)

- Re-running with the same `country_code` ⇒ `taxes_created == 0`, `fiscal_positions_created == 0`, no
  duplicate rows (FR-024).
- Switching away and back ⇒ previously created rows are reactivated, not duplicated (FR-030, FR-031).
- Zero `UPDATE`/`DELETE` on `account_move` / `account_move_line` across every path (FR-026).
- On the blocked path, row counts in `res_currency`, `account_tax`, `account_fiscal_position`, and
  `res_company` are unchanged (FR-028).
- Every branch emits a structured log line via `dodoo.core.logging` (Principle IX).
