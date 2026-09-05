# Implementation Plan: Localization & Settings

**Branch**: `005-localization-settings` | **Date**: 2026-09-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-localization-settings/spec.md`

## Summary

Add a `localization` addon (`dodoo/addons/localization/`) plus small core/base/web extensions that give an
administrator a Settings screen for the **system language** and the **company country**, and make a country
selection apply a country **localization package** (currency + taxes + fiscal positions + document
settings). Two languages ship installed — Arabic (`ar`, default, RTL) and English (`en`, LTR). UI text is
translated through an in-memory catalog: the server translates model/menu metadata per request via a
request-scoped language context; a public endpoint serves the client-string catalog the SPA loads at
bootstrap and on language change. Only Egypt has a concrete package (EGP, VAT 14% sale/purchase, VAT 0%
exempt, VAT 0% export, Domestic + Export fiscal positions, "VAT" label, round-globally). United Kingdom
(`GB`) is the seeded "neutral" country with no package. Changing country is non-destructive to posted data
and blocks a functional-currency change behind an explicit confirmation when posted entries exist. Reuses
the `account` addon's `account.tax`, `account.fiscal.position`, `res.currency`, `res.company`; introduces no
parallel tax/currency structures.

## Technical Context

**Language/Version**: Python 3.12; ES modules (vanilla JS, no framework) for the web client

**Primary Dependencies**: FastAPI 0.111, SQLAlchemy Core (async) 2.0, asyncpg 0.29, Pydantic v2 — all
existing. **Zero new runtime or dev dependencies.** Translation catalogs are plain JSON files; RTL is plain
CSS; locale formatting is hand-rolled in JS.

**Storage**: PostgreSQL via asyncpg. New tables: `res_lang`, `res_country`, `res_country_state`. Additive
columns on `res_company` (`lang`, `country_id`, `tax_label`, `tax_rounding_method`, `default_sale_tax_id`,
`default_purchase_tax_id`, `default_fiscal_position_id`) and `res_users` (`lang`, nullable). All added by
the existing additive `MigrationRunner` (`ADD COLUMN IF NOT EXISTS`).

**Testing**: pytest + pytest-asyncio (existing). Unit: effective-language resolution, catalog lookup +
English fallback, Egypt pack builder, idempotency, currency-conflict guard, locale formatters. Integration:
real PostgreSQL — migrations, `/web/i18n/*` endpoint, translated `fields_get` over JSON-RPC, Settings
save + optimistic-concurrency reject, country change with seeded posted move. E2E: Playwright — Arabic RTL
layout on login/home/list/form, language switch round-trip, Settings screen country apply.

**Target Platform**: Linux server (single-process FastAPI); modern evergreen browser for the SPA.

**Project Type**: Dodoo addon (`dodoo/addons/localization/`) + minimal `core` / `base` / `web` extensions.

**Performance Goals**:
- PERF-001: Effective-language resolution + catalog attach adds < 50 ms vs. untranslated request.
- PERF-002: Applying the Egypt package (currency + 4 taxes + 2 fiscal positions + defaults) < 3 s.
- PERF-003: No regression to accounting targets (single-record read < 500 ms; reports < 5 s). Timing
  assertions in tests guard the language-resolution path.

**Constraints**: Single company; single functional currency per company; no multi-company/multi-country; no
`product` model exists yet, so "default taxes for new products" is stored on `res.company` as the
forward-compatible hook and not wired to a product form in this cycle; Gregorian calendar retained for
Arabic; static UI strings only (no business-data translation).

**Scale/Scope**: SME scale. ~2 languages, ~20 seeded countries (enough to cover EG + GB + common
neighbours), ~5 Egyptian governorate states, 1 localization package. UI catalog on the order of 150–250
string keys.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. Code Quality**: ruff (`E,F,I,N,W,UP`, line-length 100) + Black, already enforced; zero lint
  errors on merge. New JS follows the existing `textContent`-only, ES-module style.
- [X] **II. Testing**: pytest-asyncio; ≥ 80% unit coverage; 100% branch coverage on effective-language
  resolution, Egypt pack application, idempotency check, and currency-conflict guard. Integration tests
  hit real PostgreSQL. No new mocks.
- [X] **III. Security**: SEC-001–005 in spec. Whitelist validation of `lang` (installed codes) and
  `country` (seeded codes) at the endpoint boundary. Admin-group check on every Settings/localization
  mutation; personal `lang` write restricted to the caller's own `res.users` row. Translation values
  rendered via `textContent` only (no `innerHTML`). OWASP Top 10 reviewed: A01 (broken access control) and
  A03 (injection) are the relevant classes; both mitigated. ADRs filed (see below).
- [X] **IV. Performance**: PERF-001–003 above. Company `lang` and the parsed catalogs are cached in
  process memory; resolution is one dict lookup + (cache-miss) one indexed `res_users.lang` read.
- [X] **V. Documentation**: 6 ADRs filed in `docs/adr/` (see ADR section). Inline comments explain WHY
  only. No planning docs in source.
- [X] **VI. Accessibility**: WCAG 2.1 AA in both directions; `<html lang dir>` set from the active
  language; language selector and country field keyboard-navigable; logical tab order preserved under
  RTL; errors never colour-only. Extends existing `tests/e2e/test_web_ui_a11y.py`.
- [X] **VII. Dependencies**: Zero new packages. No CVE-audit burden added.
- [X] **VIII. CI/CD**: No CI pipeline exists in dodoo yet (noted in 003) — out of scope for this cycle;
  gates enforced locally via Black + ruff + pytest.
- [X] **IX. Observability**: `dodoo.core.logging` structured JSON entries for: language-fallback events
  (user → system default), each localization-pack step, currency-conflict warnings (with company_id,
  from/to currency, posted-line count), and Settings optimistic-concurrency rejections.

## Architecture Decision Records

**ADR-018: Request-scoped language + uid via `contextvars`**
- Decision: A `dodoo/core/context.py` module exposes `ContextVar[str] lang_var` (default `"en"`) and
  `ContextVar[int | None] uid_var` (default `None`), with `get_lang()/set_lang()` and
  `get_uid()/set_uid()`. A sibling middleware (`LanguageMiddleware`, registered after
  `CorrelationMiddleware`) validates the session token once per request, sets `uid_var`, then resolves the
  effective language (`uid → res_users.lang → res_company.lang`) and sets `lang_var`.
  `BaseModel.fields_get` and `translate()` read `lang_var`; `res.config.settings.set_values` /
  `set_user_lang` / `is_admin` read `get_uid()`.
- Rationale: dodoo's `Environment` is process-wide, not per-request; threading `lang`/`uid` through every
  ORM method and the `execute_kw` dispatch would touch the entire codebase. The `_object_execute_kw`
  dispatcher currently injects `uid` **only** for `search`/`search_read`, so custom model methods invoked
  via JSON-RPC have no other way to learn the caller. A context var is the minimal, Odoo-analogous
  mechanism (Odoo propagates both through `env`).
- Alternatives rejected: (a) inject `uid` into `fields_get`/every method in the dispatcher — spreads
  plumbing and still leaves menu/system strings unsolved; (b) per-request `Environment` clone — large
  refactor, breaks existing singletons.

**ADR-019: In-memory static JSON translation catalogs (no `ir.translation`)**
- Decision: `dodoo/addons/localization/data/i18n/{ar,en}.json` (`{"key": "value"}`) are parsed once at
  addon import into a module-level dict. `translate(key, lang)` returns the value, falling back to `en`,
  then to `key`. No DB table, no translation CRUD.
- Rationale: Spec covers static UI strings only; catalogs belong with the code and version with it.
  Eliminates a model, a migration, and an editing UI.
- Alternatives rejected: `ir.translation`-style DB model (Odoo's approach) — unjustified scope for two
  fixed languages; gettext `.po` + compilation — adds tooling with no benefit here.

**ADR-020: RTL via a direction flag + `[dir=rtl]` CSS overrides**
- Decision: The SPA sets `document.documentElement.dir` / `lang` from the catalog payload. `style.css`
  uses CSS logical properties where practical and a small block of `[dir="rtl"] …` overrides for the
  sidebar, header, and breadcrumb that currently assume LTR. No build step, no second stylesheet.
- Rationale: One stylesheet, no bundler; matches the project's no-tooling front end.
- Alternatives rejected: separate `style.rtl.css` (duplication, drift); PostCSS logical-property plugin
  (new tooling, violates Principle VII).

**ADR-021: Localization packages as in-process pack definitions, not installable modules**
- Decision: A package is a Python definition (dataclass/dict) in
  `dodoo/addons/localization/packs/egypt.py` registered in a `PACKS = {"EG": ...}` map. Applying it is a
  service function that idempotently seeds records into the existing `account`/`base` models. Odoo's
  `l10n_*` are separate installable modules; dodoo has no runtime module-install-on-demand for end users,
  so a registry + apply-service is the faithful minimal analogue.
- Rationale: Keeps the "choose country → config appears" UX without a dynamic module installer; all packs
  live in one addon that depends on `account`.
- Alternatives rejected: one dodoo addon per country auto-installed on selection — needs an
  end-user-triggered installer and dependency resolution at runtime; heavy for one country.

**ADR-022: `res.config.settings` as an RPC facade**
- Decision: `res.config.settings` is a concrete model with a vestigial `id`-only table that is never
  populated (dodoo's installer does not register `_abstract` models). It exposes `get_values(env)`,
  `set_values(env, vals)`, and `set_user_lang(env, lang)` classmethods called via `execute_kw`,
  mirroring Odoo's transient settings model. `set_values` reads the caller via `get_uid()` (ADR-018), performs the admin
  check, whitelist validation, the optimistic-concurrency check against `res_company.write_date` (echoed
  in `vals["company_write_date"]`), then applies **all `res.company` field changes in a single
  `res_company.write(...)` call** and, on a country change, the pack application. dodoo's ORM commits per
  `create`/`write` (no multi-statement transaction primitive), so atomicity is guaranteed at the
  company-row level; the currency-conflict guard is a **pre-check that performs zero writes** (ADR-023),
  and pack seed rows are idempotent, so a partial pack apply converges on re-run.
- Rationale: Reuses the existing JSON-RPC surface (the SPA already speaks `execute_kw`); no new bespoke
  REST route; transient-like semantics without a transient-model framework.
- Alternatives rejected: dedicated `POST /web/settings` route (account-addon style) — a second
  auth/validation path; a real (non-abstract) settings table — pointless persistence.

**ADR-023: Currency-conflict guard keyed on posted `account.move.line` count**
- Decision: Before a pack changes `res_company.currency_id`, `set_values` counts `account_move_line`
  joined to `account_move` with `state = 'posted'`. If > 0 and the caller did not pass
  `confirm_currency_change=True`, it returns `{"warning": "currency_change_requires_confirmation", …}` and
  makes **no** changes (country included). With confirmation, or zero posted lines, it proceeds.
- Rationale: Directly implements FR-028/FR-029; "posted lines exist" is the precise, testable trigger and
  matches the accounting module's own posted-state gate.
- Alternatives rejected: block on any `account.move` existence (too broad — draft-only books should switch
  freely); allow the change and warn after (violates "does not proceed without confirmation").

## Project Structure

### Documentation (this feature)

```text
specs/005-localization-settings/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — full entity model
├── quickstart.md        # Phase 1 output — validation guide
├── contracts/           # Phase 1 output — RPC + endpoint contracts
│   ├── res_config_settings.md
│   ├── web_i18n_endpoint.md
│   └── localization_service.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
dodoo/core/
├── context.py                         # NEW: ContextVar lang_var + uid_var; get_lang/set_lang, get_uid/set_uid
└── models.py                          # EDIT: fields_get() runs field.string through translate(lang_var)

dodoo/http/
├── middleware.py                      # EDIT: LanguageMiddleware validates token → uid_var, resolves effective lang → lang_var
└── app.py                             # EDIT: register LanguageMiddleware after CorrelationMiddleware

dodoo/addons/base/models/
├── res_lang.py                        # NEW: res.lang (code, name, direction, decimal/thousands/grouping, date_format, active)
├── res_country.py                     # NEW: res.country (code, name, currency_code, phone_code, active)
├── res_country_state.py               # NEW: res.country.state (code, name, country_id)
├── res_company.py                     # EDIT: + lang (Char), country_id (Many2one res.country), tax_label (Char),
│                                      #        tax_rounding_method (Selection) — base-only refs, no account coupling
└── res_users.py                       # EDIT: + lang (Char, nullable)

# The three account-referencing company columns are added by the localization addon as plain
# INTEGER columns via DDL (ADR-005 pattern, mirrors account_data.py _PARTNER_FK_COLUMNS) — the base
# res.company model class stays free of account.* references:
#   default_sale_tax_id, default_purchase_tax_id, default_fiscal_position_id

dodoo/addons/localization/
├── __init__.py                        # imports http, models; post_install → seed_localization_data
├── __manifest__.py                    # {"name": "Localization", "depends": ["account", "web"], "application": False}
├── models/
│   ├── __init__.py
│   └── res_config_settings.py         # abstract: get_values / set_values
├── i18n.py                            # catalog loader + translate(key, lang) + fallback chain
├── locale.py                          # server-side locale metadata helpers (format tokens per lang)
├── service.py                         # apply_country_localization(env, company_id, code, *, confirm_currency_change)
├── packs/
│   ├── __init__.py                    # PACKS registry {"EG": EGYPT_PACK}
│   └── egypt.py                       # EGYPT_PACK definition (currency, taxes, fiscal positions, doc settings)
├── http/
│   └── __init__.py                    # GET /web/i18n/{lang}.json ; static mount /localization/static
├── data/
│   ├── __init__.py
│   ├── i18n/
│   │   ├── ar.json                    # Arabic UI catalog
│   │   └── en.json                    # English UI catalog (source strings)
│   ├── res_lang.py                    # seed ar + en
│   ├── res_country.py                 # seed ~20 countries incl. EG, GB
│   ├── res_country_state.py           # seed Egyptian governorates (minimal set)
│   ├── company_columns.py            # DDL: add default_sale_tax_id/default_purchase_tax_id/default_fiscal_position_id INTEGER cols
│   └── seed.py                        # seed_localization_data: langs, countries, company columns, set company country=EG (fresh), apply EG pack
└── static/
    └── views/
        └── settings.js               # #/settings screen (language + country + read-only derived config)

dodoo/addons/web/static/
├── i18n.js                            # NEW: loadCatalog() (own fetch), t(key), formatNumber/Date/Currency, applyDirection()
├── app.js                             # EDIT: bootstrap loads catalog, sets <html dir/lang>, wraps chrome strings in t(), + #/settings route
├── style.css                         # EDIT: [dir=rtl] overrides for header/sidebar/breadcrumb; logical props
└── views/{home,login,list,form}.js    # EDIT: user-facing literals → t('key')

dodoo/addons/account/static/
├── account-menu.js                    # EDIT: labels via t('key') (keys added to catalogs)
└── views/*.js                         # EDIT: user-facing literals → t('key') where present

docs/adr/
├── 006-language-contextvar.md
├── 007-static-translation-catalogs.md
├── 008-rtl-direction-flag.md
├── 009-localization-packs.md
├── 010-res-config-settings-facade.md
└── 011-currency-conflict-guard.md

tests/
├── localization/test_i18n.py                    # catalog lookup, fallback chain, locale formatters
├── localization/test_localization_packs.py      # Egypt pack builder shape, idempotency helper
├── localization/test_migrations.py              # new tables + res_company/res_users columns present
├── localization/test_localization_settings.py   # get/set_values, admin guard, optimistic concurrency, personal lang
├── localization/test_country_localization.py    # apply EG pack; re-apply idempotent; currency-conflict guard with posted move
├── localization/test_i18n_endpoint.py           # /web/i18n/{lang}.json payload; translated fields_get over JSON-RPC; <50ms budget
├── e2e/test_localization_ui.py                  # Playwright: Arabic RTL on login/home/list/form; language switch; Settings apply
└── e2e/test_web_ui_a11y.py                      # EXTEND: lang/dir attrs, RTL tab order, keyboard nav

(unit+integration localization tests grouped under tests/localization/ per the tests/accounting/ precedent)
```

**Structure Decision**: New self-contained `dodoo/addons/localization/` addon (depends on `account` + `web`)
holds the packs, i18n catalogs/loader, settings facade, and Settings screen. Reference data models
(`res.lang`, `res.country`, `res.country.state`) go in `base` alongside the other `res.*` models, matching
Odoo and ADR-005's "fundamental business objects live in base" precedent. The base `res.company` model
gains only base-referencing columns (`lang`, `country_id`, `tax_label`, `tax_rounding_method`); the three
`account.*`-referencing company columns are added by the localization addon as plain `INTEGER` via DDL
(ADR-005 pattern). The only `core` changes are the `lang_var` + `uid_var` `ContextVar`s and the
`fields_get` translation hook (ADR-018).

## Complexity Tracking

No constitution violations. The `core` changes (`fields_get` translation hook + `lang_var`/`uid_var`
`ContextVar`s) are the minimal way to (a) translate server-originated field labels without threading a
`lang` parameter through every ORM entry point, and (b) give JSON-RPC-invoked custom model methods the
caller `uid` that `_object_execute_kw` injects only for `search`/`search_read`. Both are covered by
ADR-018. The translation hook is inert when the `localization` addon is not installed (catalog empty →
`translate()` returns the source string); `uid_var` simply stays `None` outside an authenticated request.
