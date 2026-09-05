# Phase 0 Research: Localization & Settings

All spec clarifications were resolved in the `## Clarifications` section of `spec.md` (Session 2026-09-05).
This document records the remaining technical decisions needed before design.

## R1. Serving translated field labels without per-request Environment

**Decision**: Add `dodoo/core/context.py` with `lang_var: ContextVar[str]` (default `"en"`) and
`get_lang()` / `set_lang(code)`. A new `LanguageMiddleware` (Starlette `BaseHTTPMiddleware`, registered
after `CorrelationMiddleware`) reads `X-Session-Token`, resolves `uid` via `SessionManager.validate`
(swallowing auth errors → anonymous), then resolves the effective language:
`res_users.lang` (if non-empty) else cached `res_company.lang` else `"ar"` seed default. It sets `lang_var`
for the request. `BaseModel.fields_get` wraps `field.string or fname` in `translate(_, get_lang())`.

**Rationale**: `Environment` is a process singleton (`Environment.create()` once at startup); there is no
per-request env. A `ContextVar` is asyncio-safe, requires no signature changes, and mirrors Odoo's
`context['lang']` propagation. The hook is inert without the `localization` addon (empty catalog →
identity).

**Alternatives considered**:
- Inject `uid` into `fields_get` like `search`/`search_read` — only covers field labels, not menu or
  system strings, and still needs a lang lookup per call.
- Per-request `Environment` clone carrying `context` — faithful to Odoo but a large refactor of every
  model classmethod signature; rejected on scope.

## R2. Translation catalog format and load strategy

**Decision**: Flat JSON `{ "<source-or-key>": "<translation>" }` per language at
`dodoo/addons/localization/data/i18n/ar.json` and `en.json`. `i18n.py` loads both at module import into
`_CATALOGS: dict[str, dict[str, str]]`. `translate(text, lang)` → `_CATALOGS[lang].get(text)` else
`_CATALOGS["en"].get(text)` else `text`. Keys are the **English source strings** for UI chrome (so
untranslated code still reads correctly) and dotted keys (`settings.country.label`) only where a source
string would be ambiguous.

**Rationale**: Matches the "static per-language JSON files, loaded into memory" clarification. No model, no
migration, no build. English-source keys keep the fallback chain trivial and make missing-translation
behaviour (FR-008) obvious.

**Alternatives considered**: `ir.translation` DB model (Odoo) — rejected, scope; gettext `.po` +
`msgfmt` — rejected, new tooling (Principle VII).

## R3. Delivering strings + locale metadata to the SPA

**Decision**: `GET /web/i18n/{lang}.json` (`auth="public"`, `lang` path-validated against installed
codes, 400 otherwise) returns:

```json
{
  "lang": "ar",
  "direction": "rtl",
  "date_format": "%d/%m/%Y",
  "decimal_point": ".",
  "thousands_sep": ",",
  "grouping": [3, 0],
  "terms": { "Home": "الرئيسية", "Save": "حفظ", "...": "..." }
}
```

`web/static/i18n.js` exposes `loadCatalog(lang)` (fetch + cache in `sessionStorage` under
`i18n:<lang>`), `t(key)` (returns `terms[key] ?? key`), `applyDirection(direction)` (sets
`document.documentElement.dir` and `lang`), and `formatNumber` / `formatDate` / `formatCurrency` built from
the payload fields. `app.js` bootstrap: determine active lang (from `/web/core/info`, extended to include
`lang` + `direction` for the session user), `await loadCatalog(lang)`, `applyDirection(...)`, then render.

**Rationale**: One public endpoint, catalog fetched once per language and cached; mirrors Odoo's
`/web/webclient/translations` bundle. `/web/core/info` already exists and is already fetched at bootstrap —
extending it avoids a second round-trip for the "which language am I" question.

**Alternatives considered**: embed `terms` in `index.html` at serve time — couples static file serving to
DB state; per-view lazy catalogs — negligible payload here (≤ 250 keys), not worth the complexity.

## R4. Right-to-left layout

**Decision**: Direction comes from the catalog payload. `style.css` gains: (a) conversion of
`margin-left/right`, `padding-left/right`, `left/right`, `text-align` in layout rules to logical
equivalents (`margin-inline-start`, `inset-inline-start`, `text-align: start`) where supported; (b) an
explicit `[dir=rtl]` override block for the header actions order, sidebar border side, breadcrumb
separator, and the apps-grid icon. Playwright asserts computed `direction: rtl` and that the sidebar sits
on the right for Arabic.

**Rationale**: Single stylesheet, no bundler or plugin (Principle VII). Logical properties cover ~80% of
cases; the override block handles the rest deterministically.

**Alternatives considered**: separate RTL stylesheet (drift risk); `rtlcss` build step (new tooling).

## R5. Locale-aware number / date / currency formatting

**Decision**: Hand-rolled in `i18n.js` from the `res.lang` fields (`decimal_point`, `thousands_sep`,
`grouping`, `date_format`). Digits stay Western (`0-9`) for both languages — no Eastern-Arabic numeral
conversion (out of scope; keeps parity with accounting figures). `formatCurrency(amount, {symbol,
position})` places the symbol per company currency. Dates render by substituting `%d/%m/%Y`-style tokens.

**Rationale**: `Intl.NumberFormat`/`Intl.DateTimeFormat` would pull locale data we don't control and could
diverge from server-side `res.lang` seed values; explicit formatting keeps client and server identical and
testable. Zero dependency.

**Alternatives considered**: `Intl.*` APIs — rejected for determinism/parity; a formatting library —
Principle VII.

## R6. Localization package application & idempotency

**Decision**: `service.apply_country_localization(env, company_id, country_code, *,
confirm_currency_change=False) -> dict`:

1. `pack = PACKS.get(country_code)`. If `None` (e.g. `GB`): set only `res_company.country_id`; return
   `{"applied": False, "country": country_code}`.
2. Resolve target currency by `pack.currency_code`. If it differs from the company's current
   `currency_id`, count posted `account_move_line`s; if `> 0` and not `confirm_currency_change`, return
   `{"warning": "currency_change_requires_confirmation", "from": <cur>, "to": <code>, "posted_lines": n}`
   and make **no** writes.
3. Seed currency if absent (`res_currency` by `code`).
4. For each tax in `pack.taxes`: find existing `account_tax` by `(company_id, name)`; if archived,
   reactivate; if missing, create it + its `account_tax_repartition_line`s, resolving tax accounts by
   code (`2500` collected / `2510` deductible).
5. For each fiscal position in `pack.fiscal_positions`: find/create `account_fiscal_position` by
   `(company_id, name)`; create `account_fiscal_position_tax` mapping rows (Export maps 14% → 0% export).
6. Write `res_company`: `country_id`, `currency_id`, `tax_label`, `tax_rounding_method`,
   `default_sale_tax_id`, `default_purchase_tax_id`, `default_fiscal_position_id`.
7. Return `{"applied": True, "created": {...}, "reused": {...}}`.

Every create is guarded by a `(company_id, name)` existence check → re-running is a no-op (FR-024, FR-031).
All steps emit structured log lines.

**Rationale**: One service function keeps the transactional story simple and mirrors Odoo's
`_load()` / `_install_l10n` flow at a fraction of the size. Name-scoped lookups are the same idempotency
key the accounting seed helpers already use (`SELECT COUNT(*) … WHERE company_id = :cid`).

**Alternatives considered**: XML/CSV data files loaded by a generic loader (Odoo-style) — dodoo has no such
loader; Python definitions are the existing pattern (`_DEFAULT_COA`, `_DEFAULT_JOURNALS`).

## R7. Interaction with the existing generic tax seed

**Decision**: `account`'s `_seed_taxes` (generic "Tax 20.00%" sale/purchase) still runs at `account`
install. When `localization` installs afterwards on a fresh DB, `seed_localization_data` applies the Egypt
pack and **archives** the generic 20% sale/purchase taxes (`active = False`) if they have no
`account_move_line` references, then sets the Egypt 14% taxes as `res_company` defaults. Archived, never
deleted → consistent with FR-030's "retained, may be archived".

**Rationale**: Avoids a confusing fresh Egyptian install showing an unused 20% EU-style VAT as a
selectable default, without a destructive change or a dependency edit to the `account` addon.

**Alternatives considered**: modify `account`'s seed to be country-aware — couples `account` to
localization, wrong dependency direction; leave both active — poor first-run UX, ambiguous default.

## R8. Admin authorization check

**Decision**: `set_values` (and the localization mutation path) require the caller's `uid` to belong to a
group whose `name = 'Administrator'` (seeded in `base_data`). Helper `is_admin(env, uid) -> bool` does a
single `res_users_groups_rel ⋈ res_groups` query. `execute_kw` already resolves and passes `uid` for
`object` service calls after session validation; `res.config.settings.set_values` reads it the same way
`search` does (dispatch injects `uid`). Personal-language change uses a separate `set_user_lang(env, uid,
lang)` that only ever writes `res_users` row `uid` (the caller).

**Rationale**: Reuses the seeded Administrator group and the existing group-membership table; no new
permission concept. Matches SEC-002/SEC-004.

**Alternatives considered**: `ir.rule` access rules on `res.company` — heavier, and Settings is an action
not a record CRUD; a config flag — no per-user enforcement.

## R9. Seeded reference data scope

**Decision**: `res_lang`: `ar`, `en` only. `res_country`: ~20 rows — Egypt (`EG`, EGP, `+20`), United
Kingdom (`GB`, GBP, `+44`), plus common entries (US, SA, AE, FR, DE, IT, ES, JO, LB, MA, KW, QA, BH, OM,
TR, GR, IN, CN) so the Country field is realistic; each has `currency_code` + `phone_code`.
`res_country_state`: Egyptian governorates subset (Cairo, Giza, Alexandria, Dakahlia, Sharqia, Qalyubia)
as representative reference data. Only `EG` has a `PACKS` entry.

**Rationale**: FR-013/FR-014 ask for a seeded list and a "minimal representative" state set; ~20 countries
is enough to look real without a worldwide dataset, and keeps the seed file reviewable.

**Alternatives considered**: full ISO 3166 list — bulky, no functional gain; EG + GB only — Country field
looks broken.

## R10. Testing strategy for the < 50 ms resolution budget

**Decision**: `tests/integration/test_i18n_endpoint.py` measures, with `time.monotonic()`, the delta
between an untranslated baseline request and a translated `fields_get` over JSON-RPC across N=50 iterations
and asserts the mean added cost < 50 ms. Company `lang` is cached in a module-level variable invalidated on
`res_company` write; the per-request cost is then one dict `.get` plus (only on cache miss) one indexed
`res_users.lang` read.

**Rationale**: The project has no `pytest-benchmark` dependency (Principle VII); the existing e2e tests
already use `time.monotonic()` for timing assertions — same approach, no new dep.

**Alternatives considered**: add `pytest-benchmark` — new dev dependency for one metric.
