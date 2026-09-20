# Implementation Plan: Vendor Database

**Branch**: `010-vendor-database` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-vendor-database/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

This is the AP mirror of 009-customer-database, and even more of a "wire up what's already there"
feature than 009 was. `account` already carries `property_account_payable_id` and
`property_supplier_payment_term_id` as raw, undeclared `res_partner` columns
(`account_data.py::_PARTNER_FK_COLUMNS`) — added ahead of need in an earlier cycle and flagged
explicitly as "out of scope — AP side" in 009's own research.md D1 — plus `property_account_payable_id`
is already *read* (not written) by `account_payment.py`'s vendor-payment posting path. Billing
address and contact fields (`street`/`city`/`state_id`/`zip`/`country_id`/`email`/`phone`/`vat`)
already exist on `base`'s `ResPartner`, added by 009 and reused as-is — a vendor is the same
partner row as a customer, just carrying a different rank column. This feature (1) adds exactly one
new column, `supplier_rank` (Integer, default 0 — mirroring Odoo's `res.partner.supplier_rank`),
via `account`'s existing `_PARTNER_FK_COLUMNS` idiom, appended alongside `customer_rank`'s existing
entry; (2) starts writing `property_supplier_payment_term_id` and `property_account_payable_id`
for the first time (the vendor form); (3) adds one new read-only endpoint,
`GET /account/partner/{partner_id}/ap-ledger`, computing a vendor's outstanding AP balance and
bill/payment history on demand — reusing `get_ar_ledger`'s already-proven `_status_and_balance`
pure helper unmodified, only the source query differs (`in_invoice`/`in_refund`/`in_receipt` moves
against `liability_payable`-type accounts, `account_payment` rows with `partner_type='supplier'`);
and (4) ships a bespoke `vendor-list.js`/`vendor-form.js` pair, a file-for-file mirror of
`customer-list.js`/`customer-form.js`. `ResPartner.unlink`'s existing posted-reference delete guard
(009's ADR-048) is already partner-generic and needs no change — it already blocks deleting a
vendor with posted bills/payments. No new addon, no new top-level model, no new runtime dependency,
no new index (009's `idx_account_move_partner_type`/`idx_account_move_line_payment_term_move`
already cover the AP query's predicates unscoped by `move_type` value).

## Technical Context

**Language/Version**: Python 3.12 (matches 001–009; no change).

**Primary Dependencies**: FastAPI (`dodoo.http.routing.route`), SQLAlchemy Core async + asyncpg
(`dodoo.core.models.BaseModel` / `dodoo.core.fields`), Pydantic v2 (`extra="forbid"` whitelist
validators, the same stdlib `re`-based email check `CustomerCreate` already defines — reused, not
duplicated), pytest + pytest-asyncio + testcontainers. **Zero new runtime dependencies.**

**Storage**: PostgreSQL. No new tables. One new column on `res_partner`: `supplier_rank INTEGER
DEFAULT 0`, added via `account`'s existing `_PARTNER_FK_COLUMNS` raw-`ALTER TABLE` idiom in
`account_data.py`, alongside the two already-present-but-dormant `property_account_payable_id`/
`property_supplier_payment_term_id` columns this feature starts writing to. No `base`-owned
columns needed (009 already added billing address/contact fields). No stored AP-balance column
anywhere (Clarifications: computed on demand).

**Testing**: `tests/accounting/` (existing `conftest.py`), one new file
`test_vendor_database.py` covering FR-001…015 (CRUD, archive-not-delete, delete-guard-when-referenced,
search matching, AP ledger balance/history correctness against posted bills+payments,
cancelled-document exclusion, dual customer/vendor role on one partner) plus an extension of
`tests/e2e/test_web_ui_a11y.py` for the two new screens. Per `[[accounting-test-isolation]]`, the
new file reads move/payment totals across the shared test DB the same way `test_customer_database.py`
does, so it runs standalone, not batched with other `tests/accounting/` files.

**Target Platform**: Existing dodoo web server; no new deployment target.

**Project Type**: Web service + vanilla-JS SPA (existing monolith); new UI is new *content* inside
`dodoo/addons/account/static/`, following the `customer-list.js`/`customer-form.js` bespoke-view
precedent (not the generic `#/accounting/model/:model` route — ADR-051).

**Performance Goals**: PERF-001/002 (vendor list/search ≤10k records, AP ledger ≤5k lines, both
<1s) are met by **009's existing indexes with zero new ones** — confirmed by reading
`account/data/indexes.py` directly: `idx_account_move_partner_type (partner_id, move_type)` and
`idx_account_move_line_payment_term_move (move_id) WHERE display_type = 'payment_term'` are both
unscoped to a specific `move_type` *value*, so `in_invoice`/`in_refund`/`in_receipt` rows are
covered identically to `out_invoice`/`out_refund`/`out_receipt` rows (research.md D6). A benchmark
case in `tests/benchmarks/test_accounting_perf.py` confirms this empirically for the AP-ledger
query at 5,000 lines rather than assuming index reuse is sufficient. PERF-003: no regression on
bill/payment posting — the AP balance is never written at posting time (computed on demand), so
`action_post` paths are untouched by this feature.

**Constraints**: No new runtime dependencies. Migration stays additive-only (`ADD COLUMN IF NOT
EXISTS`, matching the existing `_PARTNER_FK_COLUMNS` idiom). No new HTTP route needs a group gate —
vendor CRUD is ordinary data entry, consistent with `account`'s existing decision (research.md D8,
matching 009's own D6) that pre-existing routes stay session-only and only genuinely sensitive
control actions get gated.

**Scale/Scope**: 0 new addons, 0 new tables/models. 1 new column (`supplier_rank`, via `account`'s
existing cross-addon idiom), 2 previously-dormant columns now wired up
(`property_supplier_payment_term_id`, `property_account_payable_id`), 4 new HTTP routes
(`GET /account/vendors`, `POST /account/vendor`, `PATCH /account/vendor/{id}`,
`GET /account/partner/{id}/ap-ledger`), 0 new indexes, 0 changes to `ResPartner.unlink` (already
covers this case), 2 new bespoke JS views (list + form) + 1 menu entry, 15 functional requirements
(FR-001…FR-015), 3 user stories (P1×2: US1, US3; P2×1: US2), 3 ADRs (049–051).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. Code Quality**: Same linters/formatters as 001–009 (ruff, already configured); no new
  tooling. `supplier_rank`/`property_supplier_payment_term_id` follow `_PARTNER_FK_COLUMNS`'s
  existing raw-SQL-idiom naming (`property_*` prefix, matching every column already there).
  `VendorCreate`/`VendorUpdate` follow `CustomerCreate`/`CustomerUpdate`'s exact declaration style.
- [X] **II. Testing**: `get_ap_ledger` reuses `_status_and_balance` unit-tested by 009 — no new pure
  function to add unit coverage for (research.md D5); a small additional unit case confirms it
  behaves identically when fed AP-shaped input (bill/credit_note/payment types instead of
  invoice/credit_note/payment). Integration tests cover the full CRUD + archive + delete-guard +
  AP-ledger-against-real-Postgres path in `test_vendor_database.py`, using
  `tests/accounting/conftest.py`'s existing `company_id`/`currency_id`/`payment_term_id` fixtures
  plus a new `vendor_id` fixture (mirroring `customer_id`, but via the proven
  `ResPartner.create` + `write_partner_properties` two-step — not the `customer_id` fixture's
  direct-vals-into-`create` shape, since those raw columns are silently dropped by the generic
  `create` path per `account_partner.py`'s own module docstring). E2E extends
  `test_web_ui_a11y.py` for the vendor list and form (including the AP-ledger panel). Coverage
  thresholds match 001–009's CI gate (≥80% unit, 100% on the reused `_status_and_balance` critical
  path).
- [X] **III. Security**: SEC-001…004 map to: Pydantic `extra="forbid"` validators for every field on
  the new vendor create/update payload (`VendorCreate`/`VendorUpdate` in `account/validators.py`,
  reusing the exact whitelist-boundary pattern `CustomerCreate`/`CustomerUpdate` already use) —
  closes SEC-001; existing session-auth-required dispatch already gates every model CRUD call and
  the new `ap-ledger`/`vendors`/`vendor` routes use the same `auth="session"` convention every
  other `account` route uses — closes SEC-002/SEC-004; SEC-003's OWASP review focuses on A03
  (injection) — the AP-ledger query and vendor search both use parameterized SQLAlchemy `text()`
  with bound params, the same pattern `get_ar_ledger`/`list_customers` already use, never
  string-interpolated user input.
- [X] **IV. Performance**: PERF-001/002 met via 009's existing indexes (Technical Context,
  research.md D6) — no new index, but a new benchmark case confirms it empirically rather than
  assuming. PERF-003 no-regression stated above.
- [X] **V. Documentation**: ADR-049…051 filed below (and as `docs/adr/049…051-*.md`, continuing the
  project's existing numbering from 009's ADR-048) for every non-trivial design decision. Inline
  comments follow the existing WHY-only policy, citing the ADR each query/guard implements.
- [X] **VI. Accessibility**: ACC-001…003 restate WCAG 2.1 AA; the new list/form pair reuses
  `customer-list.js`/`customer-form.js`'s existing markup/ARIA patterns (search input `aria-label`,
  keyboard-navigable rows, non-color-only validation banners) rather than inventing new
  interaction patterns.
- [X] **VII. Dependencies**: Zero new dependencies. No CVE audit or lock-file change.
- [X] **VIII. CI/CD**: Reuses the existing CI pipeline; the new test file plugs into the same
  recursive `pytest` discovery already covering `tests/accounting/`.
- [X] **IX. Observability**: Vendor create/write and the AP-ledger read log a structured entry
  (`extra={"model": "res.partner", "record_id": ..., "event": ...}`), the same shape
  `create_customer`/`update_customer`/`partner_ar_ledger` already use — no new logging
  infrastructure.

*Initial gate: PASS. Post-design re-check: PASS — Phase 1 design (data model, contract) stays
within the patterns validated above; Complexity Tracking is empty, no violations to justify.*

## Architecture Decision Records

**ADR-049: `supplier_rank` added via `account`'s existing cross-addon idiom; no new `base`-owned
fields needed**

- **Decision**: `supplier_rank` (Integer, default 0) is added as one more entry in
  `account_data.py`'s `_PARTNER_FK_COLUMNS` list (`ALTER TABLE res_partner ADD COLUMN IF NOT
  EXISTS supplier_rank INTEGER DEFAULT 0`), read/written via raw SQL from `account`'s own
  model/HTTP layer — the identical idiom 009's ADR-046 established for `customer_rank`, appended
  to the same list without touching `customer_rank`'s existing entry. No billing-address or
  contact fields are added to `base`'s `ResPartner`; this feature reuses the five fields 009 already
  added there (`street`/`city`/`state_id`/`zip`/`country_id`) plus `email`/`phone`/`vat`, since a
  vendor is the same partner row as a customer with a different rank column, not a parallel entity.
  A partner counts as a vendor when `supplier_rank > 0`, independent of `customer_rank` (FR-015).
- **Rationale**: The split mirrors Odoo's own module boundary exactly — Odoo declares
  `supplier_rank` immediately alongside `customer_rank` in `account/models/partner.py`
  (`../odoo-19.0/addons/account/models/partner.py:608`), both conceptually owned by `account`. This
  codebase's established substitute for "addon B needs a column on a table addon A owns" (raw
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` plus raw-SQL read/write) already has a proven
  extension point — 009's own `_PARTNER_FK_COLUMNS` list — and 009's research.md D3 explicitly
  anticipated this exact addition ("a future vendor-management feature can add `supplier_rank` via
  the identical idiom without touching this feature's code").
- **Alternatives rejected**: Declaring `supplier_rank` on `base`'s `ResPartner` class directly —
  rejected for the identical reason 009 rejected it for `customer_rank` (ADR-046): it would make
  `base` own an accounting-specific concept it has no reason to know about. A new
  `res.partner.vendor` side-table — rejected; would duplicate the single-rank-column concept Odoo
  itself uses and 009 already proved works for the customer side.

**ADR-050: AP ledger as an on-demand computed endpoint, reusing `get_ar_ledger`'s pure
`_status_and_balance` helper unmodified**

- **Decision**: A new module-level function, `get_ap_ledger(env, partner_id)`, placed in the same
  `dodoo/addons/account/models/account_partner.py` file as `get_ar_ledger` (both are accounting
  concerns over a `base`-owned model, per 009's ADR-047). It queries `account_move`/
  `account_move_line` for the partner's posted bills/credit notes (`move_type` in the existing
  `_PURCHASE_TYPES` from `account_move.py`) whose lines hit a `liability_payable`-type account,
  plus `account_payment` rows with `partner_type = 'supplier'` for the same partner, unions them
  into one chronological list of plain dicts in the exact shape `get_ar_ledger` already builds
  (`date`, document type, reference, `amount`, `move_id`, `amount_residual`, `_raw_status`), then
  hands that list to the **existing, unmodified** `_status_and_balance(lines)` function — no
  AP-specific variant, since that function has no AR-specific assumption anywhere in its body
  (research.md D5). Exposed via `GET /account/partner/{partner_id}/ap-ledger`. Not a
  stored/maintained field or table; computed at read time on every call, in the partner's
  `property_currency_id` (or company currency if unset) — the same single currency field 009 added,
  reused for both roles (one currency preference per partner row, not per role).
- **Rationale**: This is the exact "compute a summary on demand from source rows" convention
  `get_ar_ledger` already established for the AR side of the identical problem, and
  `AccountReportAgedPayable._aged_report(env, "liability_payable", ...)` already proves the same
  computation works against real posted vendor-bill data specifically (research.md D4). Reusing
  `_status_and_balance` verbatim avoids a near-duplicate `_ap_status_and_balance` that could drift
  from the AR version over time — the entire reason ADR-047 split that function out as pure,
  DB-free logic was to make it reusable independent of which query produced its input.
- **Alternatives rejected**: A stored, triggered `res_partner.ap_balance` column — rejected per the
  resolved Clarification, for the identical reasoning 009's ADR-047 already gives for the AR side.
  A copy-pasted `_ap_status_and_balance` — rejected as needless duplication of already-correct,
  already-unit-tested arithmetic (research.md D5).

**ADR-051: Bespoke vendor list/form views mirroring the customer pair; dedicated
`/account/vendor` create/update paths (not `/account/partner`) to avoid a validator collision**

- **Decision**: Two new files, `dodoo/addons/account/static/views/vendor-list.js` and
  `vendor-form.js`, registered in `web/static/app.js`'s `_ROUTES` table immediately after the
  existing customer routes and before the generic `#/accounting/([^/]+)$` catch-all
  (`#/accounting/vendors` → `vendor-list.js`, `#/accounting/vendor/(new|\d+)` → `vendor-form.js`) —
  the same "accounting-specific route before the generic catch-all" ordering the customer routes
  already use. `vendor-list.js` follows `customer-list.js`'s exact shape: fetch active
  `res.partner` rows with `supplier_rank > 0` via `GET /account/vendors`, client-side substring
  filter on `name`/`vat`, New button, archived toggle, each row's balance fetched via the new
  `ap-ledger` endpoint (ADR-050) per visible row. `vendor-form.js` follows `customer-form.js`'s
  field-input shape (name/email/phone/address/VAT/payment-term/currency), plus the read-only
  Accounts Payable panel (balance + bill/credit-note/payment history with drill-down to
  `#/accounting/move/{move_id}`). Vendor create/update use **new, distinct** routes —
  `POST /account/vendor` and `PATCH /account/vendor/{id}` — rather than reusing 009's
  `POST`/`PATCH /account/partner`: those paths are already bound to `create_customer`/
  `update_customer`, fixed to the `CustomerCreate`/`CustomerUpdate` Pydantic models
  (`extra="forbid"`), which would reject a vendor-shaped payload's `supplier_rank`/
  `property_supplier_payment_term_id` fields outright — a route can only dispatch to one handler,
  so vendor create/update need their own path. `GET /account/partner/{id}` (read) stays the single
  shared route both forms already use (it returns every raw column for a given id regardless of
  role, gaining two more `SELECT` columns for `supplier_rank`/`property_supplier_payment_term_id`).
  `ResPartner.unlink` (009's guard) is **not** modified — already partner-generic with no
  `move_type`/`partner_type` filter, already blocks deleting a vendor with posted bills/payments
  (research.md D7). A "Vendors" item is added to `account-menu.js`'s existing "Vendors" section
  (hash `#/accounting/vendors`), alongside its existing Bills/Credit Notes/Payments items.
- **Rationale**: `web/static/views/form.js`/`list.js` remain pure field-introspection with no
  embedded-computed-panel support, the identical constraint 009's ADR-048 already found — nothing
  about that gap is AR-specific, so it blocks a generic-route AP panel exactly the same way. The
  route-collision finding (separate `/account/vendor` path) is new to this feature, since 009 had
  no second role to collide with when it chose `/account/partner` for customer create/update.
- **Alternatives rejected**: Reusing `/account/partner`'s existing `POST`/`PATCH` with a single
  Pydantic model widened to accept every customer *and* vendor field (a `PartnerCreate` superset)
  — rejected; it would silently permit a customer-form submission to also set `supplier_rank` and
  vice versa (weakens the `extra="forbid"` whitelist's precision to "correct field, wrong route" as
  a class of bug), and would force `customer-form.js` and `vendor-form.js` to agree on one payload
  shape for no benefit — the two roles' forms are independently evolving UI, not one form. A
  generic per-model "extra panel" plugin mechanism for `web/static/views/form.js` — rejected as
  premature shared infrastructure, the same reasoning 009's ADR-048 already applied.

## Project Structure

### Documentation (this feature)

```text
specs/010-vendor-database/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── vendor-database.md     # ADR-049/050/051 (US1, US2, US3)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
dodoo/addons/account/
├── data/
│   └── account_data.py               # EDIT: _PARTNER_FK_COLUMNS + supplier_rank (ADR-049)
├── models/
│   └── account_partner.py            # EDIT: + get_ap_ledger(env, partner_id), reusing the
│                                      #   existing _status_and_balance unmodified (ADR-050);
│                                      #   + supplier_rank/property_supplier_payment_term_id to
│                                      #   write_partner_properties's _PROPERTY_COLUMNS tuple
├── validators.py                     # EDIT: + VendorCreate/VendorUpdate Pydantic models
│                                      #   (name required, email regex-validated, extra="forbid")
│                                      #   (SEC-001, FR-013)
├── http/
│   └── __init__.py                   # EDIT: + GET /account/vendors, POST /account/vendor,
│                                      #   PATCH /account/vendor/{id},
│                                      #   GET /account/partner/{id}/ap-ledger (ADR-050/051);
│                                      #   read_customer's SELECT gains supplier_rank/
│                                      #   property_supplier_payment_term_id columns
├── data/i18n/{en,ar}.json             # EDIT: new UI strings for vendor screens
│                                      #   (per [[i18n-per-addon-catalogs]])
├── static/account-menu.js            # EDIT: + "Vendors" item in the existing "Vendors" section,
│                                      #   hash #/accounting/vendors
└── static/views/
    ├── vendor-list.js                # NEW (ADR-051)
    └── vendor-form.js                # NEW: + AP-ledger panel (ADR-050/051)

dodoo/addons/web/static/
└── app.js                            # EDIT: _ROUTES + #/accounting/vendors →
                                       #   vendor-list.js, #/accounting/vendor/(new|\d+) →
                                       #   vendor-form.js, ahead of the generic
                                       #   #/accounting/([^/]+)$ catch-all (ADR-051);
                                       #   _paramsFromHash gains the vendor id-parsing branches

tests/accounting/
├── conftest.py                       # EDIT: + vendor_id fixture (supplier_rank > 0, address +
│                                      #   payment-term set, via ResPartner.create +
│                                      #   write_partner_properties — not the customer_id
│                                      #   fixture's direct-vals shape, per Constitution Check/II)
├── test_vendor_database.py           # NEW — run standalone ([[accounting-test-isolation]])
└── test_migrations.py                # EDIT: EXPECTED_COLUMNS + ("res_partner", "supplier_rank")

tests/e2e/test_web_ui_a11y.py         # EDIT: + vendor list/form WCAG checks
tests/benchmarks/test_accounting_perf.py   # EDIT: + AP-ledger query benchmark (PERF-002)

docs/adr/
├── 049-supplier-rank-cross-addon-column.md
├── 050-ap-ledger-on-demand-computed-endpoint.md
└── 051-bespoke-vendor-views-dedicated-create-update-routes.md
```

**Structure Decision**: Everything is an in-place extension of `account`, the one addon this
feature touches — one new column via its already-proven `_PARTNER_FK_COLUMNS` cross-addon idiom,
two previously-dormant columns wired up for the first time, one new read-only endpoint following
the `get_ar_ledger` on-demand-computation precedent (reusing its pure helper unmodified), two
bespoke JS views following the `customer-list.js`/`customer-form.js` precedent, and two new
create/update routes under a distinct `/account/vendor` path to avoid colliding with 009's fixed
`CustomerCreate`/`CustomerUpdate`-bound `/account/partner` routes. No new addon, no new table, no
new core infrastructure, no changes to `base` at all.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations — every decision above reuses an existing, proven pattern (raw-`ALTER TABLE`
cross-addon idiom, on-demand computed endpoint reusing an existing pure helper verbatim,
bespoke-view-for-domain-specific-UI split, unlink-guard-already-generic). Nothing in this feature
required a deviation from the constitution's principles.*
