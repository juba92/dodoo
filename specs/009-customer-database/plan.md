# Implementation Plan: Customer Database

**Branch**: `009-customer-database` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-customer-database/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Turn the existing, mostly-dormant partner infrastructure into a usable customer database: `base`'s
`ResPartner` (`dodoo/addons/base/models/res_partner.py`) already carries `name`/`company_id`/
`email`/`phone`/`vat`/`active`/`is_company`, and `account` already extends the `res_partner` table
with three unmapped columns (`property_account_receivable_id`, `property_account_payable_id`,
`property_payment_term_id`) via its existing `_PARTNER_FK_COLUMNS` raw-`ALTER TABLE` idiom
(`account_data.py`) — none of them read by any model class today. This feature (1) adds billing
address fields (`street`, `city`, `state_id`, `zip`, `country_id`) directly to `ResPartner` in
`base` — general contact attributes, matching both Odoo's own placement and this model's existing
email/phone/vat fields; (2) extends `account`'s existing `_PARTNER_FK_COLUMNS`-style idiom with two
more columns, `customer_rank` (Integer, default 0 — mirroring Odoo's `res.partner.customer_rank`,
owned by `account` exactly as Odoo owns it) and `property_currency_id` (nullable override,
NULL = company currency), and finally *reads* `property_payment_term_id`/
`property_account_receivable_id` for the first time; (3) adds one new read-only endpoint,
`/account/partner/{partner_id}/ar-ledger`, computing a customer's outstanding AR balance and
invoice/payment history on demand from `account_move`/`account_move_line`/`account_payment` —
following the exact "compute a summary on demand from source rows" convention
`AccountAccount.get_balance` already established (`/account/account/{account_id}/balance`); and
(4) ships a bespoke `customer-list.js`/`customer-form.js` pair (the `coa-list.js`/`account-form.js`
pattern) because the generic `#/accounting/model/:model` → `web/static/views/{list,form}.js` route
this codebase already uses for simpler entities (bank statements, cash rounding, lock exceptions,
analytic accounts) is pure field-introspection with no support for a computed cross-model panel —
insufficient for User Story 3's AR ledger view. `ResPartner.unlink` gains the same
"posted-reference blocks delete" guard `AccountMove.unlink` already has, adapted to check
`account_move`/`account_payment` rows instead of `state`. No new addon, no new top-level model, no
new runtime dependency — every piece attaches to a table, endpoint pattern, or guard this codebase
already has proof for.

## Technical Context

**Language/Version**: Python 3.12 (matches 001–008; no change).

**Primary Dependencies**: FastAPI (`dodoo.http.routing.route`), SQLAlchemy Core async + asyncpg
(`dodoo.core.models.BaseModel` / `dodoo.core.fields`), Pydantic v2 (`extra="forbid"` whitelist
validators, plain `str`/regex email check — **not** `pydantic[email]`/`EmailStr`, since no field in
this codebase uses it today and FR-013 doesn't warrant a new dependency), pytest + pytest-asyncio +
testcontainers. **Zero new runtime dependencies.**

**Storage**: PostgreSQL. No new tables. New columns on `res_partner`: five plain `Field`
additions declared directly on `base`'s `ResPartner` class (`street` Char, `city` Char, `state_id`
Many2one `res.country.state`, `zip` Char, `country_id` Many2one `res.country`) — same-owner
addition, matching Odoo's own `base`-owned address fields; plus two columns added via `account`'s
existing `_PARTNER_FK_COLUMNS` raw-`ALTER TABLE` idiom in `account_data.py` (`customer_rank
INTEGER DEFAULT 0`, `property_currency_id INTEGER`) — cross-addon, same idiom already used for the
three `property_account_*`/`property_payment_term_id` columns already there. No stored AR-balance
column anywhere (Clarifications: computed on demand).

**Testing**: `tests/accounting/` (existing `conftest.py` already has a `partner_id` fixture to
extend), one new file `test_customer_database.py` covering FR-001…014 (CRUD, archive-not-delete,
delete-guard-when-referenced, search matching, AR ledger balance/history correctness against
posted invoices+payments, cancelled-document exclusion) plus an extension of
`tests/e2e/test_web_ui_a11y.py` for the two new screens. Per `[[accounting-test-isolation]]`, the
new file reads move/payment totals across the shared test DB the same way `test_account_balance.py`
does, so it runs standalone like the existing balance/report test files.

**Target Platform**: Existing dodoo web server; no new deployment target.

**Project Type**: Web service + vanilla-JS SPA (existing monolith); new UI is new *content* inside
`dodoo/addons/account/static/`, following the `coa-list.js`/`account-form.js` bespoke-view
precedent (not the generic `#/accounting/model/:model` route — see ADR-048).

**Performance Goals**: PERF-001/002 (customer list/search ≤10k records, AR ledger ≤5k
lines, both <1s) are met by two `(partner_id, ...)`-scoped queries reusing `account_move_line`'s
existing `idx_account_move_line_account_reconciled` shape: a new
`idx_account_move_line_partner_account` composite index `(partner_id, account_id)` on
`account_move_line` (added via `account/data/indexes.py`'s existing `ensure_indexes` helper) lets
the AR-ledger query filter to one partner's receivable-account lines without a sequential scan; the
customer list's balance column reuses the same index grouped by `partner_id`. PERF-003: no
regression on invoice/payment posting — the AR balance is never written at posting time (Clarified:
computed on demand), so `action_post` paths are untouched by this feature.

**Constraints**: No new runtime dependencies. Migrations stay additive-only (`ADD COLUMN IF NOT
EXISTS`, matching the existing `_PARTNER_FK_COLUMNS` idiom). No new HTTP route needs a group gate —
customer CRUD is ordinary data entry, consistent with `account`'s existing decision (research.md D8
of 008-accounting-parity / `account/security.py`'s own docstring) that pre-existing routes stay
session-only and only genuinely sensitive control actions get gated; nothing about creating/editing
a customer record is a sensitive action.

**Scale/Scope**: 0 new addons, 0 new tables/models. 7 new columns total (5 on `res_partner` via
`base`, 2 via `account`'s existing cross-addon idiom), 1 new HTTP route
(`GET /account/partner/{id}/ar-ledger`), 1 new index, 1 `ResPartner.unlink` override, 2 new bespoke
JS views (list + form) + 1 menu entry, 14 functional requirements (FR-001…FR-014), 3 user stories
(P1×2: US1, US3; P2×1: US2), 3 ADRs (046–048).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. Code Quality**: Same linters/formatters as 001–008 (ruff, already configured); no new
  tooling. New fields follow `ResPartner`'s existing `snake_case`/`Field()` declaration style; the
  two `account`-owned columns follow `_PARTNER_FK_COLUMNS`'s existing raw-SQL-idiom naming
  (`property_*` prefix, matching the three columns already there).
- [X] **II. Testing**: Unit-level coverage for pure logic (AR-ledger balance arithmetic against a
  fixed set of invoice/payment/cancellation fixtures, search-matching predicate). Integration tests
  cover the full CRUD + archive + delete-guard + AR-ledger-against-real-Postgres path in
  `test_customer_database.py`, using `tests/accounting/conftest.py`'s existing `company_id`/
  `currency_id`/`journal_sale`/`ar_account`/`partner_id` fixtures. E2E extends
  `test_web_ui_a11y.py` for the customer list and form (including the AR-ledger panel). Coverage
  thresholds match 001–008's CI gate (≥80% unit, 100% on the AR-balance computation critical path).
- [X] **III. Security**: SEC-001…004 map to: Pydantic `extra="forbid"` validators for every field on
  the new customer create/update payload (`CustomerCreate`/`CustomerUpdate` in
  `account/validators.py`, reusing the whitelist-boundary pattern every other validator in that file
  already follows) — closes SEC-001; existing session-auth-required dispatch (`jsonrpc_handler`)
  already gates every model CRUD call and the new `ar-ledger` route uses the same `auth="session"`
  convention every other `account` route uses — closes SEC-002/SEC-004; SEC-003's OWASP review
  focuses on A03 (injection) — the AR-ledger query and the customer search both use parameterized
  SQLAlchemy `text()` with bound params, the same pattern every existing report/balance query in
  `account_report.py`/`account_account.py` already uses, never string-interpolated user input.
- [X] **IV. Performance**: PERF-001/002 index strategy and PERF-003 no-regression stated above;
  a new `test_customer_database.py` benchmark case (or an addition to
  `tests/benchmarks/test_accounting_perf.py`) exercises the AR-ledger query at 5,000 lines.
- [X] **V. Documentation**: ADR-046…048 filed below (and as `docs/adr/046…048-*.md`, continuing the
  project's existing numbering from 008's ADR-045) for every non-trivial design decision. Inline
  comments follow the existing WHY-only policy (e.g. citing which ADR a query/guard implements, the
  precedent `account_move.py`'s `"""Round-globally tax computation (ADR-003)."""` already sets).
- [X] **VI. Accessibility**: ACC-001…003 restate WCAG 2.1 AA; the new list/form pair reuses
  `coa-list.js`/`account-form.js`'s existing markup/ARIA patterns (search input `aria-label`,
  keyboard-navigable rows, non-color-only validation banners via `_showBanner`-style helpers) rather
  than inventing new interaction patterns.
- [X] **VII. Dependencies**: Zero new dependencies (Technical Context above — email format is
  checked with a stdlib `re` pattern in a Pydantic `field_validator`, not `EmailStr`). No CVE audit
  or lock-file change.
- [X] **VIII. CI/CD**: Reuses the existing CI pipeline; the new test file plugs into the same
  recursive `pytest` discovery already covering `tests/accounting/`.
- [X] **IX. Observability**: Customer create/write/unlink and the AR-ledger read log a structured
  entry (`extra={"model": "res.partner", "record_id": ..., "event": ...}`), the same shape
  `AccountMove.action_post`/`AccountPartialReconcile.reconcile_lines` already use — no new logging
  infrastructure.

*Initial gate: PASS. Post-design re-check: PASS — Phase 1 design (data model, contract) stays
within the patterns validated above; Complexity Tracking is empty, no violations to justify.*

## Architecture Decision Records

**ADR-046: Customer fields split across `base` (address) and `account` (accounting-specific), via
each addon's existing ownership idiom**

- **Decision**: Billing-address fields (`street`, `city`, `state_id`, `zip`, `country_id`) are
  declared directly on `base`'s `ResPartner` class as plain `Field`s — a same-owner addition, no new
  idiom needed, exactly like the existing `email`/`phone`/`vat` fields already on that class.
  `customer_rank` (Integer, default 0) and `property_currency_id` (Many2one `res.currency`,
  nullable — `NULL` means "use `res_company.currency_id`") are instead added the same way `account`
  already extends `res_partner` today: two more entries in `account_data.py`'s
  `_PARTNER_FK_COLUMNS` list (`ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS customer_rank
  INTEGER DEFAULT 0`, `... property_currency_id INTEGER`), read/written via raw SQL from `account`'s
  own model/HTTP layer rather than a declared `Field` on `ResPartner` — not first-class ORM columns
  on the `base`-owned class, matching exactly how `property_account_receivable_id`/
  `property_account_payable_id`/`property_payment_term_id` already work. A partner counts as a
  customer when `customer_rank > 0`.
- **Rationale**: The split mirrors Odoo's own module boundary exactly — Odoo's `base/…/res_partner.py`
  owns `street`/`city`/`zip`/`country_id`/`vat`/`email`/`phone`, while `customer_rank` and the
  `property_*` AR/payment-term fields are declared in `account/models/partner.py`
  (`../odoo-19.0/addons/account/models/partner.py:606-607,543-557`), i.e. conceptually owned by
  `account` even though they live on the same `res.partner` row. This codebase has no Python
  `_inherit` mechanism to add fields to another addon's model class, so its own established
  substitute — raw `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` plus raw-SQL read/write from the
  owning addon — is the existing, proven answer (used today for exactly this: the three
  `property_*` columns account already added). Reusing that idiom for two more columns needs no new
  mechanism, no new migration pattern, and requires touching only one existing list.
- **Alternatives rejected**: Declaring `customer_rank`/`property_currency_id` on `base`'s
  `ResPartner` class directly (simpler — one file, real ORM `Field`) — rejected because it would
  make `base` own an accounting-specific concept `base` has no reason to know about, the same
  reasoning 008-accounting-parity's ADR-039/042 already applied when choosing `ALTER TABLE` over a
  new `base`-owned field for lock dates and FX-gain-loss accounts. A new `res.partner.customer`
  side-table (`partner_id` FK + customer-only fields) — rejected; it would duplicate the "is a
  customer" concept Odoo itself keeps as a plain rank field on the one partner row, and would need
  a join everywhere a customer's rank is checked instead of one column read.

**ADR-047: AR ledger as an on-demand computed endpoint, not a stored entity**

- **Decision**: A new `AccountReportPartnerLedger`-style helper — in practice a plain classmethod,
  `ResPartner.get_ar_ledger(env, partner_id)` (in `account`'s own `models/`, since `res.partner`
  itself lives in `base` but this method is an accounting concern — placed as a module-level
  function in a new `dodoo/addons/account/models/account_partner.py`, not a change to `base`'s
  `ResPartner` class) — queries `account_move`/`account_move_line` for the partner's posted
  invoices/credit notes (`move_type` in the existing `_SALE_TYPES`) whose lines hit an
  `asset_receivable`-type account, plus `account_payment` rows for the same partner, unions them
  into one chronological list (`date`, document type, reference/`name`, `amount`, computed
  paid/partial/open status from the line's existing `amount_residual`, `move_id` for drill-down),
  and sums open lines' `amount_residual` for the balance — all in the partner's `property_currency_id`
  (or company currency if unset). Exposed via `GET /account/partner/{partner_id}/ar-ledger`. Not a
  stored/maintained field or table; computed at read time on every call.
- **Rationale**: This is the exact "compute a summary on demand from source rows" convention
  `AccountAccount.get_balance` already established (`account_account.py`, backing
  `/account/account/{account_id}/balance`) and the read-time `is_complete` check
  `AccountBankStatement.get_status` uses (008's ADR-043) — both already proven, tested patterns for
  "give the UI one number/list derived from posted ledger rows, computed at read time." Using
  `amount_residual` (already populated by every existing posting/reconciliation path per
  008-accounting-parity) instead of re-deriving payment status from scratch means the AR ledger's
  "paid/partial/open" status can never drift from what reconciliation has already computed.
- **Alternatives rejected**: A stored, triggered `res_partner.ar_balance` column recomputed on every
  invoice/payment/reconciliation write — rejected per the resolved Clarification (avoids a second
  write path across four different posting flows that could drift, the same reasoning
  008's ADR-043 used to reject a stored/triggered `is_complete` boolean for bank statements). A
  general-purpose "partner ledger" report class reusable for both AR and AP in one call — rejected
  as premature generalization; this feature only needs the customer (AR) side, and
  `AccountReportAgedReceivable`/`AccountReportAgedPayable` already show the two sides don't share a
  single query shape in this codebase.

**ADR-048: Bespoke customer list/form views, not the generic `#/accounting/model/:model` route; a
delete guard mirroring `AccountMove.unlink`**

- **Decision**: Two new files, `dodoo/addons/account/static/views/customer-list.js` and
  `customer-form.js`, registered in `web/static/app.js`'s `_ROUTES` table ahead of the generic
  `#/accounting/model/([^/]+)` patterns (`#/accounting/customers` → `customer-list.js`,
  `#/accounting/customer/(new|\d+)` → `customer-form.js`), the same "accounting-specific route
  before the generic model route" ordering `#/accounting/chart-of-accounts`/`#/accounting/account/…`
  already use ahead of `#/accounting/model/…`. `customer-list.js` follows `coa-list.js`'s exact
  shape: fetch active `res.partner` rows with `customer_rank > 0`, client-side substring filter on
  `name`/`vat` (PERF-001's 10k-row budget is well within what `coa-list.js` already does for the
  chart of accounts), New button, archived toggle; each row's balance column is fetched via the new
  `ar-ledger` endpoint (ADR-047) batched per visible page. `customer-form.js` follows
  `account-form.js`'s field-input shape for the master-data fields, plus one additional read-only
  panel rendering `get_ar_ledger`'s response as a table (date/reference/amount/status, each row
  linking to `#/accounting/move/{move_id}`) — the same drill-down navigation
  008-accounting-parity's `report-view.js` already added for report rows (ADR-044). A new
  `ResPartner.unlink` classmethod override (`base/models/res_partner.py`) checks, per id, whether
  any `account_move` or `account_payment` row has `partner_id = id`; if so it raises `DodooError`
  (FR-006) with the same message shape `AccountMove.unlink` already uses for its posted-move guard,
  otherwise delegates to `super().unlink()`. Archiving (FR-005) needs no new code — `active` already
  exists on `ResPartner` and every existing list already filters on it by convention.
- **Rationale**: `web/static/views/form.js`/`list.js` are pure field-introspection (verified: no
  support for an embedded computed panel or extra action button beyond Save/Discard/Delete) — the
  four entities currently routed through the generic path (bank statements, cash rounding, lock
  exceptions, analytic accounts) are all plain-CRUD-only in the SPA today, but User Story 3 (P1) is
  specifically the AR-ledger *view*, which the generic form cannot render. Building bespoke views
  only where a domain-specific view genuinely differs from plain-CRUD (as `coa-list.js`/
  `account-form.js`/`invoice-form.js` already do) rather than for every entity keeps this consistent
  with the codebase's own existing split, not a new pattern.
- **Alternatives rejected**: Extending the generic `web/static/views/form.js` with a per-model
  "extra panel" plugin mechanism so bank statements, lock exceptions, *and* customers could all use
  it — rejected as new shared infrastructure disproportionate to one feature's need, and out of step
  with how every other domain-specific view (COA, invoices) already just has its own file. A
  `res.partner`-wide `ResPartner.unlink` override living in `account` instead of `base` (keeping
  `base` guard-free) — rejected; `unlink` must live on the class SQLAlchemy dispatch actually calls
  (`ResPartner` in `base`), and `base` has no dependency on `account`'s tables to query — the guard
  necessarily lives where the model class lives, exactly like `AccountMove.unlink` lives on
  `AccountMove` itself, not in a separate addon.

## Project Structure

### Documentation (this feature)

```text
specs/009-customer-database/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── customer-database.md   # ADR-046/047/048 (US1, US2, US3)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
dodoo/addons/base/models/
└── res_partner.py                    # EDIT: + street/city/state_id/zip/country_id Fields
                                       #   (ADR-046); + unlink() classmethod override checking
                                       #   account_move/account_payment references (ADR-048, FR-006)

dodoo/addons/account/
├── data/
│   ├── account_data.py               # EDIT: _PARTNER_FK_COLUMNS + customer_rank,
│   │                                  #   property_currency_id (ADR-046)
│   ├── indexes.py                    # EDIT: + idx_account_move_line_partner_account
│   │                                  #   (partner_id, account_id) — PERF-001/002
│   └── i18n/{en,ar}.json              # EDIT: new UI strings for customer screens
│                                      #   (per [[i18n-per-addon-catalogs]])
├── models/
│   ├── account_partner.py            # NEW: ResPartner.get_ar_ledger(env, partner_id) (ADR-047)
│   └── __init__.py                   # EDIT: import + register the new module
├── validators.py                     # EDIT: + CustomerCreate/CustomerUpdate Pydantic models
│                                      #   (name required, email regex-validated, extra="forbid")
│                                      #   (SEC-001, FR-013)
├── http/
│   └── __init__.py                   # EDIT: + GET /account/partner/{partner_id}/ar-ledger
│                                      #   (ADR-047)
├── account-menu.js                   # EDIT: + "Customers" item in the existing "Customers"
│                                      #   section, hash #/accounting/customers
└── static/
    └── views/
        ├── customer-list.js          # NEW (ADR-048)
        └── customer-form.js          # NEW: + AR-ledger panel (ADR-047/048)

dodoo/addons/web/static/
└── app.js                            # EDIT: _ROUTES + #/accounting/customers →
                                       #   customer-list.js, #/accounting/customer/(new|\d+) →
                                       #   customer-form.js, ahead of the generic
                                       #   #/accounting/model/… patterns (ADR-048)

tests/accounting/
├── conftest.py                       # EDIT: extend/add a customer_id fixture
│                                      #   (customer_rank > 0, address + payment-term set)
└── test_customer_database.py         # NEW — run standalone
                                       #   ([[accounting-test-isolation]], reads AR totals across
                                       #   the shared test DB like test_account_balance.py)

tests/e2e/test_web_ui_a11y.py         # EDIT: + customer list/form WCAG checks
tests/benchmarks/test_accounting_perf.py   # EDIT: + AR-ledger query benchmark (PERF-002)

docs/adr/
├── 046-customer-fields-base-account-split.md
├── 047-ar-ledger-on-demand-computed-endpoint.md
└── 048-bespoke-customer-views-unlink-guard.md
```

**Structure Decision**: Everything is an in-place extension of two addons this codebase already
owns and already has the exact idioms for — `base` gains five ordinary `Field`s on `ResPartner`
(same-owner addition, no new idiom) and one `unlink` guard; `account` gains two more columns via its
own already-proven `_PARTNER_FK_COLUMNS` cross-addon idiom, one new read-only endpoint following the
`get_balance`/`get_status` on-demand-computation precedent, and two bespoke JS views following the
`coa-list.js`/`account-form.js` precedent. No new addon, no new table, no new core infrastructure.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations — every decision above reuses an existing, proven pattern (raw-`ALTER TABLE`
cross-addon idiom, on-demand computed endpoint, bespoke-view-for-domain-specific-UI split,
`unlink`-guard-on-owning-class). Nothing in this feature required a deviation from the
constitution's principles.*
