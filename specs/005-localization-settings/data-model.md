# Phase 1 Data Model: Localization & Settings

Field types refer to `dodoo/core/fields.py`. New tables are created by `MigrationRunner`; new columns on
existing tables are added additively (`ADD COLUMN IF NOT EXISTS`). All monetary/precision concerns are
inherited from the `account` addon unchanged.

## New models (in `dodoo/addons/base/models/`)

### `res.lang` — installed UI language

| Field | Type | Notes |
|-------|------|-------|
| `code` | `Char(16)`, required | `ar`, `en`. Unique in practice (enforced by seed idempotency). |
| `name` | `Char(64)`, required | "العربية", "English". |
| `direction` | `Selection([('ltr','LTR'),('rtl','RTL')])`, required | `ar → rtl`, `en → ltr`. |
| `decimal_point` | `Char(4)`, default `"."` | Decimal separator for display. |
| `thousands_sep` | `Char(4)`, default `","` | Group separator. |
| `grouping` | `Char(16)`, default `"[3,0]"` | JSON-ish grouping spec (string; parsed client-side). |
| `date_format` | `Char(32)`, default `"%d/%m/%Y"` | strftime-style tokens. |
| `active` | `Boolean`, default `True` | "installed" flag. Both seeded rows are active. |

**Seed**: exactly two rows — `en` (ltr) and `ar` (rtl). Idempotent on `code`.

### `res.country` — country reference data

| Field | Type | Notes |
|-------|------|-------|
| `code` | `Char(2)`, required | ISO 3166-1 alpha-2, uppercase. `EG`, `GB`, … |
| `name` | `Char(128)`, required | Display name; translatable via the UI catalog, not stored per-lang. |
| `currency_code` | `Char(3)`, required | ISO 4217 of the country's default currency (`EGP`, `GBP`). |
| `phone_code` | `Char(8)` | International dialing prefix without `+` (`20`, `44`). |
| `active` | `Boolean`, default `True` | |

**Seed**: ~20 rows (see research R9), including `EG` (EGP, 20) and `GB` (GBP, 44). Idempotent on `code`.

### `res.country.state` — country subdivision reference data

| Field | Type | Notes |
|-------|------|-------|
| `country_id` | `Many2one('res.country')`, required | Parent country. |
| `code` | `Char(8)`, required | Subdivision code, unique within the country. |
| `name` | `Char(128)`, required | e.g. "Cairo". |

**Seed**: a minimal Egyptian governorate set (Cairo, Giza, Alexandria, Dakahlia, Sharqia, Qalyubia).
Idempotent on `(country_id, code)`.

## Extended model: `res.company`

### Columns on the base `res.company` model class (base-only references)

| Field | Type | Notes |
|-------|------|-------|
| `lang` | `Char(16)`, default `"ar"` | **System default language.** Fallback in effective-language resolution (FR-004, FR-006). |
| `country_id` | `Many2one('res.country')` | Selected company country. Set to Egypt on fresh install (FR-016). |
| `tax_label` | `Char(16)`, default `"VAT"` | Label shown on documents (FR-022). Egypt → "VAT". |
| `tax_rounding_method` | `Selection([('round_globally','Round Globally'),('round_per_line','Round per Line')])`, default `"round_globally"` | Egypt → round globally (FR-034). Mirrors ADR-003 of the accounting module. |

### Columns added by the `localization` addon as plain `INTEGER` via DDL

`ADD COLUMN IF NOT EXISTS … INTEGER`, mirroring `account_data.py::_PARTNER_FK_COLUMNS`. They are **not**
declared on the base `res.company` model class, keeping `base` free of `account.*` references (ADR-005).
`res.config.settings.get_values` / `set_values` read and write them by raw column; `apply_country_localization`
sets them.

| Column | Meaning |
|--------|---------|
| `default_sale_tax_id` | Default sale tax for new products (FR-022). Egypt → "VAT 14%" sale. |
| `default_purchase_tax_id` | Default purchase tax for new products. Egypt → "VAT 14%" purchase. |
| `default_fiscal_position_id` | Active default (domestic) fiscal position (FR-023). |

`write_date` (already present) is the **optimistic-concurrency token** for Settings saves (FR-033). All
`res.company` field changes from a single Settings save are applied in **one `res_company.write(...)`
call** (company-row-level atomicity; dodoo's ORM has no multi-statement transaction — see ADR-010).

## Extended model: `res.users` (add column)

| Field | Type | Notes |
|-------|------|-------|
| `lang` | `Char(16)`, nullable, default `None` | Personal language preference. Empty/NULL ⇒ use `res.company.lang` (FR-003, FR-005, FR-006). Set to the system default at user-create time when omitted. |

## New abstract model: `res.config.settings` (in `dodoo/addons/localization/models/`)

`_abstract = True` — no table. Classmethods callable via `execute_kw` (ADR-010): `get_values(env)`,
`set_values(env, vals)`, `set_user_lang(env, lang)`. The caller `uid` is **not** an argument — the
`_object_execute_kw` dispatcher injects `uid` only for `search`/`search_read`, so these methods read the
caller via `dodoo.core.context.get_uid()`, which `LanguageMiddleware` sets from the validated session
token (ADR-006). `is_admin()` and the personal-language write both use `get_uid()`. See
`contracts/res_config_settings.md`.

| Logical field (in `get_values` payload) | Source |
|-----------------------------------------|--------|
| `lang` | `res_company.lang` |
| `country_id` / `country_code` | `res_company.country_id` → `res_country` |
| `available_langs` | `res_lang` where `active` |
| `available_countries` | `res_country` where `active` |
| `tax_label`, `tax_rounding_method` | `res_company` (read-only; pack-derived) |
| `default_sale_tax_id`, `default_purchase_tax_id`, `default_fiscal_position_id` | `res_company` (read-only; pack-derived) |
| `company_write_date` | `res_company.write_date` (concurrency token echoed back on save) |

## Localization package definition (not persisted — Python, `dodoo/addons/localization/packs/egypt.py`)

```text
Pack:
  country_code:            "EG"
  currency:                {code: "EGP", name: "Egyptian Pound", symbol: "£", rounding: 2}
  tax_label:               "VAT"
  tax_rounding_method:     "round_globally"
  tax_group:               "VAT"
  taxes: [
    {key: "eg_vat_14_sale",   name: "VAT 14%",            type_tax_use: "sale",     amount_type: "percent", amount: 14, tax_account_code: "2500"},
    {key: "eg_vat_14_purch",  name: "VAT 14% (Purchase)", type_tax_use: "purchase", amount_type: "percent", amount: 14, tax_account_code: "2510"},
    {key: "eg_vat_0_exempt",  name: "VAT 0% (Exempt)",    type_tax_use: "sale",     amount_type: "percent", amount: 0,  tax_account_code: null},
    {key: "eg_vat_0_export",  name: "VAT 0% (Export)",    type_tax_use: "sale",     amount_type: "percent", amount: 0,  tax_account_code: null},
  ]
  fiscal_positions: [
    {name: "Domestic", tax_maps: []},
    {name: "Export",   tax_maps: [
        {src: "eg_vat_14_sale",  dest: "eg_vat_0_export"},
        {src: "eg_vat_14_purch", dest: "eg_vat_0_export"},
    ]},
  ]
  defaults:
    default_sale_tax_key:      "eg_vat_14_sale"
    default_purchase_tax_key:  "eg_vat_14_purch"
    default_fiscal_position:   "Domestic"
```

`PACKS = {"EG": EGYPT_PACK}`. `GB` (and every other seeded country) has **no** entry ⇒ neutral (FR-017).

## Records created in existing `account` models when the Egypt pack applies

| Model | Rows | Idempotency key |
|-------|------|-----------------|
| `res.currency` | `EGP` (if absent) | `code` |
| `account.tax.group` | `VAT` | `(company_id, name)` |
| `account.tax` | 4 (VAT 14% sale, VAT 14% purchase, VAT 0% Exempt, VAT 0% Export) | `(company_id, name)` — reactivate if archived |
| `account.tax.repartition.line` | base+tax lines for the two 14% taxes (tax line → `2500` / `2510`); base-only for the 0% taxes | parent `tax_id` + `sequence` |
| `account.fiscal.position` | 2 (`Domestic`, `Export`) | `(company_id, name)` |
| `account.fiscal.position.tax` | 2 rows on `Export` (14% sale/purchase → 0% export) | `(position_id, tax_src_id)` |

The generic `account`-seeded "Tax 20.00%" sale/purchase taxes are set `active = False` on fresh install if
unreferenced (research R7). Nothing is deleted.

## State & lifecycle

- **Effective language** (per request): `res_users.lang` if non-empty → else `res_company.lang` → else
  `"ar"` (seed default). Resolved in `LanguageMiddleware`; stored in `lang_var` ContextVar.
- **Country change**: `draft` implication only — no state machine. `apply_country_localization` is a
  transactional operation with three outcomes: `applied` (writes committed), `neutral` (only
  `country_id` written), `blocked` (returns `warning`, no writes — awaits `confirm_currency_change`).
- **Idempotency**: re-applying the same (or a previously applied) country creates no duplicate rows;
  archived pack records are reactivated (FR-024, FR-031).
- **Posted-data safety**: `apply_country_localization` never issues `UPDATE`/`DELETE` against
  `account_move`, `account_move_line`, or posted `account.tax.repartition.line` rows (FR-026).

## Validation rules

| Rule | Enforced where |
|------|----------------|
| `lang` ∈ active `res_lang.code` | `set_values` / `set_user_lang` / `/web/i18n/{lang}.json` — 400/`DodooError` otherwise (SEC-001) |
| `country_code` ∈ active `res_country.code` | `set_values` — `DodooError` otherwise (SEC-001) |
| caller is Administrator | `set_values`, `apply_country_localization` entry — `AccessError` otherwise (SEC-002/004) |
| personal `lang` write targets only the caller's `res_users` row | `set_user_lang` (SEC-004) |
| `company_write_date` in save payload == current `res_company.write_date` | `set_values` — else `DodooError("settings_stale")` (FR-033) |
| currency change + posted lines + no confirm ⇒ no writes | `apply_country_localization` (FR-028) |
| translation value rendered as text | SPA `t()` returns a string assigned via `textContent` only (SEC-005) |
