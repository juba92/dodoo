# Contract: `res.config.settings` (JSON-RPC via `execute_kw`)

Concrete model with a vestigial `id`-only table, never populated (ADR-022; dodoo's installer does not
register `_abstract` models). All calls go through the existing `/jsonrpc` endpoint,
`params.service = "object"`, `params.method = "execute_kw"`,
`args = [model, method, method_args]`. Session token in `X-Session-Token`.

**Caller identity**: `_object_execute_kw` injects `uid` into `kwargs` only for `search` / `search_read`.
These methods therefore take **no `uid` argument** — they read the caller via
`dodoo.core.context.get_uid()`, which `LanguageMiddleware` populates from the validated session token
before the RPC handler runs (ADR-018). An unauthenticated call fails session validation before reaching
the method.

## `get_values() -> object`

**Call**: `execute_kw("res.config.settings", "get_values", [])`

**Auth**: any authenticated user (read-only). Non-admins receive the same payload; the SPA renders the
mutating controls only for admins.

**Result**:

```json
{
  "lang": "ar",
  "country_id": 3,
  "country_code": "EG",
  "tax_label": "VAT",
  "tax_rounding_method": "round_globally",
  "default_sale_tax_id": 11,
  "default_purchase_tax_id": 12,
  "default_fiscal_position_id": 4,
  "company_write_date": "2026-09-05T10:12:33",
  "available_langs": [
    {"code": "ar", "name": "العربية", "direction": "rtl"},
    {"code": "en", "name": "English", "direction": "ltr"}
  ],
  "available_countries": [
    {"id": 3, "code": "EG", "name": "Egypt", "currency_code": "EGP"},
    {"id": 7, "code": "GB", "name": "United Kingdom", "currency_code": "GBP"}
  ]
}
```

## `set_values(vals) -> object`

**Call**: `execute_kw("res.config.settings", "set_values", [vals])`

**Auth**: **Administrator group required** → `AccessError` (JSON-RPC code `-32000`) otherwise.

**`vals`**:

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `lang` | string | no | Must be an active `res_lang.code`. Writes `res_company.lang`. |
| `country_code` | string | no | Must be an active `res_country.code`. Triggers `apply_country_localization`. |
| `confirm_currency_change` | bool | no (default `false`) | Pass `true` to proceed past a currency-conflict warning. |
| `company_write_date` | string | **yes** | Echo of the value from `get_values`. Optimistic-concurrency token. |

**Behaviour** (dodoo's ORM commits per `write` — no multi-statement transaction; order is chosen so the
only "decline" path performs zero writes):
1. Admin check via `get_uid()` → `AccessError` if not admin.
2. Whitelist `lang` / `country_code` → `DodooError` (code `-32602`) on unknown value.
3. `company_write_date` ≠ current `res_company.write_date` → `DodooError("settings_stale")`; **no writes**.
4. If `country_code` present and differs from current → **first** run the currency-conflict pre-check
   inside `apply_country_localization(..., confirm_currency_change=…)`. If it returns a `warning`,
   `set_values` returns that warning object immediately — **nothing has been written yet** (no `lang`
   write, no `country_id` write). Otherwise `apply_country_localization` seeds the idempotent pack rows
   and returns the company-field values to write.
5. Apply **all** `res.company` changes (`lang` if present, plus `country_id` / `currency_id` /
   `tax_label` / `tax_rounding_method` / `default_*` from step 4) in a **single `res_company.write(...)`
   call** — company-row-level atomicity.
6. On success, return the fresh `get_values()` payload plus the `"applied"` summary:

```json
{
  "ok": true,
  "applied": {"country": "EG", "currency": "EGP", "taxes_created": 4, "taxes_reused": 0,
              "fiscal_positions_created": 2, "archived_generic_taxes": 2},
  "settings": { "...": "same shape as get_values()" }
}
```

**Currency-conflict warning result** (HTTP 200, JSON-RPC `result`, not an error):

```json
{
  "ok": false,
  "warning": "currency_change_requires_confirmation",
  "detail": {"from": "EUR", "to": "EGP", "posted_lines": 128},
  "settings": { "... unchanged ..." }
}
```

The SPA shows a confirm dialog and re-calls `set_values` with `confirm_currency_change: true`.

## `set_user_lang(lang) -> object`

**Call**: `execute_kw("res.config.settings", "set_user_lang", ["en"])`

**Auth**: any authenticated user; writes **only** the caller's own `res_users.lang` row (SEC-004).

**`lang`**: must be an active `res_lang.code`, or empty string / `null` to clear the personal preference
(revert to system default).

**Result**: `{"ok": true, "lang": "en", "effective_lang": "en", "direction": "ltr"}`

## Error codes (existing JSON-RPC convention)

| Condition | code | `data.type` |
|-----------|------|-------------|
| Not authenticated / expired | `-32000` | `AuthenticationError` |
| Not an administrator | `-32000` | `AccessError` |
| Unknown `lang` / `country_code`, stale settings | `-32602` | `DodooError` |
| Unexpected server error | `-32603` | (exception class name) |
