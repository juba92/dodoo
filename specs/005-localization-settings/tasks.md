---
description: "Task list for Localization & Settings implementation"
---

# Tasks: Localization & Settings

**Input**: Design documents from `specs/005-localization-settings/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the project constitution (Principle II) mandates unit + integration + e2e coverage
with enforced thresholds, and plan.md commits to specific test tasks.

**Organization**: Tasks are grouped by user story. Each user story phase is an independently testable
increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 / US4 (from spec.md). Setup, Foundational, and Polish carry no story label.
- Exact file paths are included in every task.

## Path Conventions

Dodoo addon layout: new addon at `dodoo/addons/localization/`, reference models in
`dodoo/addons/base/models/`, minimal `dodoo/core/` + `dodoo/http/` edits, tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `localization` addon skeleton so models can register and the module can install.

- [ ] T001 Create `dodoo/addons/localization/__manifest__.py` with `{"name": "Localization", "version": "1.0.0", "depends": ["account", "web"], "application": False}`
- [ ] T002 Create the addon package tree with empty `__init__.py` files: `dodoo/addons/localization/__init__.py` (will import `http`, `models` and define `post_install`), `models/__init__.py`, `packs/__init__.py`, `http/__init__.py`, `data/__init__.py`, `data/i18n/`, `static/views/`
- [ ] T003 [P] Add `tests/localization/__init__.py` and `tests/localization/conftest.py` re-exporting the shared `env` / `pg_engine` fixtures from `tests/conftest.py`. All localization **unit + integration** tests live under `tests/localization/` (mirrors the `tests/accounting/` precedent); e2e tests stay in `tests/e2e/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reference-data models, the language context + resolver, the translation layer, and the seed
pipeline. **No user story can start until this phase is complete.**

### Core language context

- [ ] T004 Create `dodoo/core/context.py` exposing `lang_var: ContextVar[str]` (default `"en"`) and `uid_var: ContextVar[int | None]` (default `None`), with `get_lang()/set_lang(code)` and `get_uid()/set_uid(uid)` (ADR-006). The `_object_execute_kw` dispatcher is **not** modified — custom model methods read the caller via `get_uid()`
- [ ] T005 Edit `dodoo/core/models.py` — in `BaseModel.fields_get`, wrap `field.string or fname` through a `translate(value, get_lang())` call imported lazily so `core` has no hard dependency on the `localization` addon (returns the source string when no catalog is loaded)

### Reference-data models (base addon)

- [ ] T006 [P] Create `dodoo/addons/base/models/res_lang.py` — `res.lang` model: `code` Char(16) required, `name` Char(64) required, `direction` Selection(ltr/rtl) required, `decimal_point` Char(4) default ".", `thousands_sep` Char(4) default ",", `grouping` Char(16) default "[3,0]", `date_format` Char(32) default "%d/%m/%Y", `active` Boolean default True (per data-model.md)
- [ ] T007 [P] Create `dodoo/addons/base/models/res_country.py` — `res.country` model: `code` Char(2) required, `name` Char(128) required, `currency_code` Char(3) required, `phone_code` Char(8), `active` Boolean default True
- [ ] T008 [P] Create `dodoo/addons/base/models/res_country_state.py` — `res.country.state` model: `country_id` Many2one("res.country") required, `code` Char(8) required, `name` Char(128) required
- [ ] T009 Edit `dodoo/addons/base/models/res_company.py` — add **base-only** columns: `lang` Char(16) default "ar", `country_id` Many2one("res.country"), `tax_label` Char(16) default "VAT", `tax_rounding_method` Selection(round_globally/round_per_line) default "round_globally". Do **not** add `account.*` Many2one fields here — that would couple `base` to `account` (ADR-005); the three account-referencing columns are added by the localization addon in T019 as plain INTEGER (mirrors `account_data.py::_PARTNER_FK_COLUMNS`)
- [ ] T010 Edit `dodoo/addons/base/models/res_users.py` — add `lang` Char(16) nullable (no default); in `create`, when `vals` omits `lang`, leave it NULL (empty ⇒ system default per FR-003/FR-006)
- [ ] T011 Edit `dodoo/addons/base/models/__init__.py` to import `res_lang`, `res_country`, `res_country_state`

### Translation layer (localization addon)

- [ ] T012 [P] Create `dodoo/addons/localization/data/i18n/en.json` — English source catalog seeded with all UI-chrome keys used across `app.js`, `views/{login,home,list,form}.js`, and `account/static/account-menu.js` (identity mapping: `"Home": "Home"`, `"Save": "Save"`, `"Settings": "Settings"`, `"Country": "Country"`, `"Language": "Language"`, …)
- [ ] T013 [P] Create `dodoo/addons/localization/data/i18n/ar.json` — Arabic translations for every key present in `en.json`
- [ ] T014 Create `dodoo/addons/localization/i18n.py` — load `data/i18n/{ar,en}.json` at import into `_CATALOGS`; `translate(text, lang)` returns `_CATALOGS[lang].get(text)` → `_CATALOGS["en"].get(text)` → `text` (FR-008); `catalog(lang)` returns the full dict (ADR-007)
- [ ] T015 [P] Create `dodoo/addons/localization/locale.py` — `locale_meta(lang)` returns `{direction, date_format, decimal_point, thousands_sep, grouping}` read from the `res.lang` row (parses `grouping` string to a list)

### Seed data (localization addon)

- [ ] T016 [P] Create `dodoo/addons/localization/data/res_lang.py` — `seed_langs(env)`: idempotently upsert `en` (ltr) and `ar` (rtl, default) on `code`
- [ ] T017 [P] Create `dodoo/addons/localization/data/res_country.py` — `seed_countries(env)`: idempotently upsert ~20 countries incl. `EG` (EGP, "20") and `GB` (GBP, "44") on `code` (list per research.md R9)
- [ ] T018 [P] Create `dodoo/addons/localization/data/res_country_state.py` — `seed_states(env)`: idempotently upsert the Egyptian governorate subset (Cairo, Giza, Alexandria, Dakahlia, Sharqia, Qalyubia) on `(country_id, code)`
- [ ] T019 Create `dodoo/addons/localization/data/seed.py` — `seed_localization_data(env)`: (1) `ALTER TABLE res_company ADD COLUMN IF NOT EXISTS default_sale_tax_id INTEGER` (and `default_purchase_tax_id`, `default_fiscal_position_id`) — the ADR-005 pattern; (2) call `seed_langs`, `seed_countries`, `seed_states`; (3) fresh-install branch, guarded by "company has no `country_id`": set the company `country_id` to Egypt and invoke `apply_country_localization(env, company_id, "EG")` — the pack call is wired in **T055** (leave a documented TODO import until then)
- [ ] T020 Edit `dodoo/addons/localization/__init__.py` — `from dodoo.addons.localization import http, models` and `async def post_install(env): await seed_localization_data(env)`

### Request-scoped language resolution + core info

- [ ] T021 Edit `dodoo/http/middleware.py` — add `LanguageMiddleware(BaseHTTPMiddleware)` that resolves `uid` from `X-Session-Token` (swallowing `AuthenticationError` → anonymous), calls `set_uid(uid)`, then resolves effective language `res_users.lang or res_company.lang or "ar"` and calls `set_lang(code)`; cache the company `lang` in a module-level var invalidated on `res_company` write
- [ ] T022 Edit `dodoo/http/app.py` — register `LanguageMiddleware` after `CorrelationMiddleware`
- [ ] T023 [P] Create `dodoo/addons/localization/models/res_config_settings.py` — abstract model `res.config.settings` (`_abstract = True`) with `is_admin(env, uid)` classmethod helper (single `res_users_groups_rel ⋈ res_groups WHERE name='Administrator'` query) and a `get_values(env)` classmethod (reads the caller via `dodoo.core.context.get_uid()` where needed) returning the payload in `contracts/res_config_settings.md` (lang, country, derived read-only fields incl. the three INTEGER `default_*` columns, `company_write_date`, `available_langs`, `available_countries`)
- [ ] T024 Edit `dodoo/addons/localization/models/__init__.py` to import `res_config_settings`
- [ ] T025 Edit `dodoo/addons/base/http/__init__.py` — extend `GET /web/core/info` response with `lang`, `direction`, and `is_admin` for the calling session (anonymous ⇒ system default; per `contracts/web_i18n_endpoint.md`)

### Client i18n module + catalog endpoint

- [ ] T026 Create `dodoo/addons/localization/http/__init__.py` — `@route("/web/i18n/{lang}.json", methods=["GET"], auth="public")` returning the payload in `contracts/web_i18n_endpoint.md` (400 on unknown/inactive `lang`, 503 on DB failure); `MountRegistry.add_mount("/localization/static", StaticFiles(...))`
- [ ] T027 [P] Create `dodoo/addons/web/static/i18n.js` — `loadCatalog(lang)` (fetch `/web/i18n/<lang>.json`, cache in `sessionStorage` key `i18n:<lang>`), `t(key)` (`terms[key] ?? key`), `applyDirection(direction)` (sets `document.documentElement.dir` + `lang`), `formatNumber`/`formatDate`/`formatCurrency` built from the payload fields (research R5; digits stay Western)

### Foundational tests

- [ ] T028 [P] Create `tests/localization/test_migrations.py` asserting `res_lang`, `res_country`, `res_country_state` tables exist and `res_company` (incl. the three `default_*` INTEGER columns) / `res_users` gained the new columns after `module install localization`
- [ ] T029 [P] Create `tests/localization/test_i18n.py` — `translate()` hit, `ar`→`en` fallback, `en`→key fallback; `formatNumber`/`formatDate`/`formatCurrency` parity fixtures (mirror the JS formatter rules)
- [ ] T030 [P] Create `tests/localization/test_i18n_endpoint.py` — `GET /web/i18n/ar.json` returns `direction: "rtl"` + non-empty `terms`; `GET /web/i18n/en.json` returns `ltr`; `GET /web/i18n/fr.json` → 400; assert `< 50 ms` mean added cost of a translated `fields_get` over JSON-RPC vs. baseline across N=50 iterations (PERF-001)

**Checkpoint**: Reference data seeds, effective language resolves per request, `fields_get` labels are
translatable, and the client can fetch a catalog. User stories can now begin.

---

## Phase 3: User Story 1 — Configure system language & localized RTL/LTR UI (Priority: P1) 🎯 MVP

**Goal**: An administrator sets the system default language in Settings; all users without a personal
preference see the whole UI translated, RTL for Arabic / LTR for English, with locale-formatted
numbers/dates/amounts, effective on the next page load without re-login.

**Independent Test**: Fresh install → login/home/list/form render Arabic RTL. Set language to English in
Settings → reload → same screens render English LTR with locale-correct dates/amounts; no missing labels.

- [ ] T031 [US1] Add `set_values(env, vals)` to `dodoo/addons/localization/models/res_config_settings.py` — reads caller via `get_uid()`; admin check `is_admin(env, get_uid())` (`AccessError`), whitelist `lang` against active `res_lang.code` (`DodooError`), optimistic-concurrency check `vals["company_write_date"] == res_company.write_date` (`DodooError("settings_stale")`, no writes), then apply the `lang` change via a single `res_company.write(...)`; return fresh `get_values()` + `{"ok": true}` (contract: `res_config_settings.md`; country path added in T056)
- [ ] T032 [P] [US1] Create `dodoo/addons/localization/static/views/settings.js` — `#/settings` screen: renders `get_values()`, a Language `<select>` (from `available_langs`), a Save button calling `execute_kw("res.config.settings","set_values",[{lang, company_write_date}])`; on success re-calls `loadCatalog` + `applyDirection` and re-renders; shows `settings_stale` as an inline error with a Reload action. Country field placeholder wired in T048
- [ ] T033 [US1] Edit `dodoo/addons/web/static/app.js` — bootstrap: after `getInfo()`, read `info.lang`/`info.direction`, `await loadCatalog(info.lang)`, `applyDirection(info.direction)` before first `_route()`; add `[/^#\/settings$/, () => import('/localization/static/views/settings.js')]` to `_ROUTES`; add a Settings entry to the sidebar/user-area
- [ ] T034 [US1] Edit `dodoo/addons/web/static/app.js` — wrap user-facing chrome literals in `t(...)`: `_ACC_LABELS` values, `_labelFromHash` outputs, sidebar section titles ("Models"), `"Home"`/`"Login"` breadcrumb seeds, nav `aria-label`s, logout `title`, app name fallback
- [ ] T035 [P] [US1] Edit `dodoo/addons/web/static/views/login.js` — literals ("Sign in to your account", "Login", "Password", "Log in", "Signing in…", expired-session banner, error fallbacks) → `t(...)`; set the login page container `dir` from the bootstrapped direction
- [ ] T036 [P] [US1] Edit `dodoo/addons/web/static/views/home.js` — module display names, "Loading modules…", "No modules installed.", "Failed to load modules", `aria-label`s → `t(...)`
- [ ] T037 [P] [US1] Edit `dodoo/addons/web/static/views/list.js` — column headers, action buttons, empty/loading/error states → `t(...)`; render monetary + date cells through `formatCurrency`/`formatDate`
- [ ] T038 [P] [US1] Edit `dodoo/addons/web/static/views/form.js` — labels, Save/Discard/Create buttons, validation messages → `t(...)`; render monetary/date fields through the formatters
- [ ] T039 [P] [US1] Edit `dodoo/addons/account/static/account-menu.js` — section + item labels → `t(...)`; add the corresponding keys to `en.json`/`ar.json`
- [ ] T040 [US1] Edit `dodoo/addons/web/static/style.css` — convert directional layout rules (`margin/padding-left|right`, `left|right`, `text-align`) to logical properties where supported; add a `[dir=rtl]` override block for header action order, sidebar side/border, breadcrumb separator, apps-grid icon, login card (ADR-008)
- [ ] T041 [US1] Fill `dodoo/addons/localization/data/i18n/ar.json` + `en.json` with every key introduced in T034–T039; add structured `dodoo.core.logging` lines in `LanguageMiddleware` (user→system fallback) and `set_values` (save + `settings_stale` reject)
- [ ] T042 [P] [US1] Create `tests/localization/test_localization_settings.py` — `get_values`/`set_values` happy path for `lang`; admin guard rejects a non-admin (`AccessError`); stale `company_write_date` → `DodooError("settings_stale")` with no write; effective language flips for a preference-less user on the next request
- [ ] T043 [P] [US1] Create `tests/e2e/test_localization_ui.py` — Playwright: fresh install renders login + home + list + form in Arabic with computed `direction: rtl` and sidebar on the right; via Settings switch to English → screens render `ltr` in English without re-login; a sampled date + amount use locale formatting (SC-001, SC-002, SC-009)
- [ ] T044 [P] [US1] Extend `tests/e2e/test_web_ui_a11y.py` — assert `<html lang>`/`dir` set correctly per language, language `<select>` is keyboard-navigable, tab order stays logical under RTL, errors are not colour-only (ACC-001–003)

**Checkpoint**: US1 is independently shippable — a working Arabic-first, direction-aware, translated UI
with an admin language switch. **This is the MVP.**

---

## Phase 4: User Story 2 — Personal language preference override (Priority: P2)

**Goal**: A user sets a personal language; their sessions render in it regardless of the system default,
without affecting other users; clearing it reverts to the system default.

**Independent Test**: System default = Arabic. User A sets personal = English → every screen for A is
English LTR while User B (no preference) still sees Arabic RTL in a concurrent session.

- [ ] T045 [US2] Add `set_user_lang(env, lang)` to `dodoo/addons/localization/models/res_config_settings.py` — reads caller via `get_uid()`; validate `lang` against active `res_lang.code` OR empty/`None` (clear); write **only** the `res_users` row for `get_uid()` (SEC-004); return `{"ok": true, "lang", "effective_lang", "direction"}` (contract: `res_config_settings.md`)
- [ ] T046 [US2] Edit `dodoo/http/middleware.py` `LanguageMiddleware` — confirm precedence `res_users.lang` (non-empty) → `res_company.lang` → `"ar"`; treat a personal `lang` not in active `res_lang` as empty (edge case in spec)
- [ ] T047 [P] [US2] Edit `dodoo/addons/localization/static/views/settings.js` — add a "My language" control (visible to every user) bound to `set_user_lang`, with a "Use system default" option that sends an empty value; on success re-`loadCatalog` + `applyDirection` for the current user only
- [ ] T048 [US2] Edit `dodoo/addons/web/static/app.js` — after a personal-language change, refresh the catalog/direction without a full reload path regression; ensure `getInfo()` `lang` reflects the personal preference
- [ ] T049 [P] [US2] Edit `dodoo/addons/localization/data/i18n/{ar,en}.json` — add "My language" / "Use system default" keys; add a structured log line for personal-language changes
- [ ] T050 [P] [US2] Add to `tests/localization/test_localization_settings.py` — User A personal `en` while system `ar`: A's `/web/core/info` and a translated `fields_get` return English; User B unaffected; a new user created via `execute_kw("res.users","create",…)` without `lang` resolves to the system default (SC-003, SC-010); clearing A's preference reverts to Arabic
- [ ] T051 [P] [US2] Add to `tests/e2e/test_localization_ui.py` — personal override round-trip in the browser: set personal English, navigate several screens (all LTR/English), then "Use system default" restores Arabic RTL

**Checkpoint**: US1 + US2 deliver full language configuration (system + personal).

---

## Phase 5: User Story 3 — Select a country & auto-apply its localization package (Priority: P2)

**Goal**: Selecting the company country applies the country package — functional currency, sales/purchase
taxes mapped to tax accounts, domestic + export fiscal positions, tax label, rounding method, and default
product taxes — and sets them as the active company defaults. Fresh install already has Egypt applied.

**Independent Test**: On a company set to United Kingdom, select Egypt in Settings → EGP is the functional
currency, the four Egypt taxes + two fiscal positions exist and are defaults, tax label reads "VAT",
re-selecting Egypt creates no duplicates.

- [ ] T052 [P] [US3] Create `dodoo/addons/localization/packs/egypt.py` — `EGYPT_PACK` per data-model.md: EGP currency, `VAT 14%` sale (→ `2500`), `VAT 14% (Purchase)` purchase (→ `2510`), `VAT 0% (Exempt)`, `VAT 0% (Export)`, `Domestic` + `Export` fiscal positions (Export maps both 14% taxes → 0% export), `tax_label="VAT"`, `tax_rounding_method="round_globally"`, default sale/purchase tax keys, default fiscal position "Domestic"
- [ ] T053 [US3] Create `dodoo/addons/localization/packs/__init__.py` — `PACKS = {"EG": EGYPT_PACK}`; helper `get_pack(country_code)` → pack or `None`
- [ ] T054 [US3] Create `dodoo/addons/localization/service.py` — `apply_country_localization(env, company_id, country_code, *, confirm_currency_change=False)`: neutral branch (no pack → write only `country_id`, return `{"applied": false}`); applied branch — seed `res_currency` by `code` if absent, upsert `account.tax.group` "VAT" by `(company_id,name)`, upsert the 4 `account.tax` by `(company_id,name)` (reactivate if archived) with `account.tax.repartition.line` base+tax rows resolving accounts by code, upsert 2 `account.fiscal.position` + `account.fiscal.position.tax` maps, write the 7 `res_company` fields; return the applied summary in `contracts/localization_service.md`. Structured log per step. (Currency-conflict guard is T060.)
- [ ] T055 [US3] Edit `dodoo/addons/localization/data/seed.py` — replace the T019 TODO: import and call `apply_country_localization(env, company_id, "EG")` in the fresh-install branch; then archive (`active=False`) the `account`-seeded generic `Tax 20.00%` sale/purchase taxes when they have zero `account_move_line` references (research R7)
- [ ] T056 [US3] Extend `set_values` in `dodoo/addons/localization/models/res_config_settings.py` — handle `country_code`: whitelist against active `res_country.code`; when it differs from the current company country, call `apply_country_localization(...)` **before** any write (its currency-conflict pre-check, added in US4, returns a `warning` with zero writes); on success, gather the company-field values it returns and apply them **together with** the `lang` change in the single `res_company.write(...)` call from T031; include the `applied` summary in the `set_values` result
- [ ] T057 [P] [US3] Edit `dodoo/addons/localization/static/views/settings.js` — add the Country `<select>` (from `available_countries`, rendering each `name` through `t(...)` so it localizes), and a read-only panel showing `tax_label`, `tax_rounding_method`, `default_sale_tax_id`, `default_purchase_tax_id`, `default_fiscal_position_id` from `get_values()`; Save sends `country_code` alongside `lang` + `company_write_date`; render the `applied` summary as a confirmation toast
- [ ] T058 [P] [US3] Edit `dodoo/addons/localization/data/i18n/{ar,en}.json` — add country names shown in the selector and the settings panel labels ("Tax Label", "Rounding Method", "Default Sales Tax", …)
- [ ] T059 [P] [US3] Create `tests/localization/test_localization_packs.py` — `EGYPT_PACK` shape assertions: 4 taxes with correct `type_tax_use`/`amount`, tax→account code mapping, Export fiscal position maps 14%→0% export, defaults reference the 14% taxes; idempotency-key helper returns existing id when a `(company_id,name)` row exists
- [ ] T060 [P] [US3] Create `tests/localization/test_country_localization.py` — fresh install: company `country_id`=Egypt, EGP is `currency_id`, 4 Egypt taxes + 2 fiscal positions exist and are the `res_company` defaults, generic 20% taxes archived (SC-004); on a UK company, `set_values(country_code="EG")` applies the full pack (SC-005) and completes in `< 3 s`; calling it again creates 0 new tax/currency/fiscal rows (SC-006, FR-024)

**Checkpoint**: US1 + US2 + US3 — language configuration plus country-driven currency & tax setup on a
clean or fresh install.

---

## Phase 6: User Story 4 — Change country safely after accounting data exists (Priority: P3)

**Goal**: Changing country after taxes/fiscal positions/posted entries exist adds the new config and
switches defaults without touching posted data; a functional-currency change with posted entries needs
explicit confirmation; declining aborts with no side effects; prior packs are retained (archived) and
reused on switch-back.

**Independent Test**: Egypt applied + one posted EGP journal entry. Change country to United Kingdom (GBP)
→ warning returned, zero row changes. Re-call with confirmation → succeeds; posted entry unchanged; Egypt
taxes archived not deleted; switch back to Egypt reactivates them with no duplicates.

- [ ] T061 [US4] Edit `dodoo/addons/localization/service.py` — add the currency-conflict guard: before any write, if the pack's currency differs from `res_company.currency_id` AND `COUNT(account_move_line ⋈ account_move WHERE state='posted') > 0` AND not `confirm_currency_change`, return `{"applied": false, "warning": "currency_change_requires_confirmation", "from", "to", "posted_lines"}` and perform **no** writes (not even `country_id`) — FR-028; with confirmation or zero posted lines, proceed (FR-029)
- [ ] T062 [US4] Edit `dodoo/addons/localization/service.py` — switch-away behaviour: when moving to a different country, do not delete/deactivate posted-referenced records; on switch to a previously applied country, reactivate archived `(company_id,name)` rows instead of creating new ones (FR-030, FR-031); guarantee no `UPDATE`/`DELETE` on `account_move`/`account_move_line` on any path (FR-026)
- [ ] T063 [US4] Edit `set_values` in `dodoo/addons/localization/models/res_config_settings.py` — accept `confirm_currency_change` (default false) and pass it to `apply_country_localization`; because the currency-conflict pre-check runs **before** the single `res_company.write(...)`, a `warning` return means nothing has been written yet — return `{"ok": false, "warning", "detail", "settings": get_values()}` with the `lang` change also not applied (contract: `res_config_settings.md`)
- [ ] T064 [P] [US4] Edit `dodoo/addons/localization/static/views/settings.js` — on an `{ok:false, warning:"currency_change_requires_confirmation"}` result, show a confirm dialog naming the from/to currency and posted-line count; on confirm, re-call `set_values` with `confirm_currency_change:true`; on cancel, revert the Country `<select>` to its saved value
- [ ] T065 [P] [US4] Edit `dodoo/addons/localization/data/i18n/{ar,en}.json` — add the currency-conflict dialog strings; add a structured `dodoo.core.logging` warning line in the guard (company_id, from, to, posted_lines)
- [ ] T066 [P] [US4] Add to `tests/localization/test_country_localization.py` — apply Egypt, post a journal entry in EGP, `set_values(country_code="GB")` → `{ok:false, warning}` and row counts in `res_currency`/`account_tax`/`account_fiscal_position`/`res_company` unchanged (SC-008); re-call with `confirm_currency_change=true` → succeeds, the posted entry's amounts/currency/taxes are byte-identical (SC-007), Egypt taxes are `active=False` not deleted; `set_values(country_code="EG")` again reactivates them, 0 duplicates (FR-031); a country change with an empty ledger switches currency with no warning (FR-029)
- [ ] T067 [P] [US4] Add to `tests/e2e/test_localization_ui.py` — in the browser: with data present, changing Country triggers the confirm dialog; cancelling leaves the selector and config unchanged; confirming applies and shows the summary

**Checkpoint**: All four user stories complete — full Localization & Settings capability.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: ADRs, coverage, lint, docs, and cross-cutting validation.

- [ ] T068 [P] Write ADR files `docs/adr/006-language-contextvar.md`, `007-static-translation-catalogs.md`, `008-rtl-direction-flag.md`, `009-localization-packs.md`, `010-res-config-settings-facade.md`, `011-currency-conflict-guard.md` (title/status/context/decision/consequences) matching plan.md
- [ ] T069 [P] Add a localization-addon overview docstring/`README` note in `dodoo/addons/localization/__init__.py` (what it installs, the pack registry, the two translation paths)
- [ ] T070 Run `ruff check` + `black --check` across `dodoo/core/context.py`, `dodoo/http/middleware.py`, `dodoo/addons/base/models/res_*.py`, `dodoo/addons/localization/**`, and new tests; fix all findings (Principle I)
- [ ] T071 Verify coverage: `pytest --cov` ≥ 80% for `dodoo/addons/localization/`; 100% branch coverage on `i18n.translate`, `service.apply_country_localization` (all three outcomes), the currency-conflict guard, and `LanguageMiddleware` effective-language resolution (Principle II)
- [ ] T072 [P] Confirm zero new dependencies: `pip-audit` clean and `pyproject.toml` unchanged (Principle VII)
- [ ] T073 [P] Execute `specs/005-localization-settings/quickstart.md` end-to-end against a fresh DB; fix any drift between the guide and the implementation
- [ ] T074 [P] Accessibility pass: WCAG 2.1 AA contrast check on the Settings screen and RTL chrome in both light and default themes; verify the `#status` aria-live announcements still fire under RTL (Principle VI / ACC-001–003)
- [ ] T075 OWASP Top 10 review (Principle III / SEC-003): document in `docs/adr/` or a review note that A01 (broken access control — every Settings/`set_values`/`apply_country_localization` path re-checks `is_admin(env, get_uid())` server-side; `set_user_lang` writes only the caller's row) and A03 (injection — `lang`/`country_code` whitelisted at the boundary; seed/catalog data is static and parameterized; translation values rendered via `textContent`, never `innerHTML` — grep the changed JS to confirm) are addressed; record any residual risk
- [ ] T076 Regression check: run the full existing suite (`tests/e2e/test_web_ui.py`, `tests/accounting/`, `tests/integration/`) to confirm the `fields_get` hook, middleware, and `/web/core/info` changes did not break the accounting UI or JSON-RPC contracts (PERF-003)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → no dependencies.
- **Foundational (Phase 2)** → depends on Setup. **BLOCKS all user stories.**
- **US1 (Phase 3)** → depends on Foundational. The MVP.
- **US2 (Phase 4)** → depends on Foundational; independent of US1 in principle but shares
  `settings.js` / `app.js` / catalogs, so sequence US2 after US1 to avoid merge churn.
- **US3 (Phase 5)** → depends on Foundational; shares `set_values` / `settings.js` with US1. Sequence
  after US1. Independent of US2.
- **US4 (Phase 6)** → **depends on US3** (extends `service.py` and the `set_values` country path).
- **Polish (Phase 7)** → depends on all targeted stories being complete.

### Story-level independent test criteria

| Story | Independently testable when… |
|-------|------------------------------|
| US1 | Foundational + Phase 3 done — admin switches system language, UI is translated + direction-aware, formatters localized |
| US2 | Foundational + Phase 4 done — personal preference overrides system default, no cross-user leakage |
| US3 | Foundational + Phase 5 done — selecting a country applies currency + taxes + fiscal positions as defaults, idempotently |
| US4 | US3 + Phase 6 done — country change is non-destructive to posted data and gated on currency-conflict confirmation |

### Key blocking tasks

- T004–T005 (language + uid context vars + `fields_get` hook) block every translation task and every
  `set_values` / `set_user_lang` / `is_admin` task (they read `get_uid()` — the RPC dispatcher is not
  changed).
- T006–T011 (models/columns) block all seeds, services, and `get_values`.
- T014 (`i18n.py`) blocks T005's runtime behaviour, T026, T027, all `t(...)` tasks.
- T019–T020 (seed pipeline + `default_*` INTEGER columns + `post_install`) block every integration test.
- T021–T022 (`LanguageMiddleware` → `uid_var` + `lang_var`) block US1/US2 effective-language behaviour
  and the admin check.
- T054 (`service.apply_country_localization`) blocks T055, T056, and all of US4.

---

## Parallel Execution Examples

### Phase 2 — after T004–T005 and T006–T011 land

```
# Reference model files are independent:
T006  dodoo/addons/base/models/res_lang.py
T007  dodoo/addons/base/models/res_country.py
T008  dodoo/addons/base/models/res_country_state.py

# Then translation + seed + client, all different files:
T012  data/i18n/en.json      T013  data/i18n/ar.json
T015  localization/locale.py  T016  data/res_lang.py
T017  data/res_country.py     T018  data/res_country_state.py
T027  web/static/i18n.js
```

### Phase 3 (US1) — after T031 and T033/T034 land

```
T035  views/login.js    T036  views/home.js
T037  views/list.js     T038  views/form.js
T039  account/static/account-menu.js
# Tests in parallel once the views are wrapped:
T042  tests/localization/test_localization_settings.py
T043  tests/e2e/test_localization_ui.py
T044  tests/e2e/test_web_ui_a11y.py
```

### Phase 5 (US3) — after T054 lands

```
T057  static/views/settings.js (country field)
T058  data/i18n/{ar,en}.json (country keys)
T059  tests/localization/test_localization_packs.py
T060  tests/localization/test_country_localization.py
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Complete Phase 3 (US1).
3. **STOP and validate**: fresh install is Arabic RTL; admin can switch to English LTR; no missing
   labels; dates/amounts localized. This is a shippable increment (SC-001, SC-002, SC-009).

### Incremental delivery

1. Add US2 → personal language overrides (SC-003, SC-010). Ship.
2. Add US3 → country-driven currency + taxes + fiscal positions, Egypt pack, fresh-install seeding
   (SC-004, SC-005, SC-006). Ship.
3. Add US4 → safe country change, currency-conflict guard, archive/reactivate (SC-007, SC-008). Ship.
4. Phase 7 polish throughout / before final merge.

### Notes

- `[P]` tasks touch distinct files with no incomplete-task dependency.
- Every task names its file path; commit per task or per small `[P]` group.
- Constitution gates (lint, coverage, a11y, zero new deps) are enforced in Phase 7 but should be kept
  green continuously.
