---

description: "Task list for Customer Database implementation"
---

# Tasks: Customer Database

**Input**: Design documents from `specs/009-customer-database/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the constitution requires ≥80% unit / 100% critical-path branch coverage, and
this feature's own success criteria (SC-004, SC-005) are only verifiable with test coverage of the
AR-balance computation and the CRUD/archive/delete-guard paths.

**Organization**: Tasks are grouped by the three user stories from spec.md, in priority order
(P1: US1, US3; P2: US2). FR-to-story mapping (all 14 FRs, each assigned once): US1={FR-001,002,005,
006,007,011,013,014}, US2={FR-003,004}, US3={FR-008,009,010,012}. Note: FR-003 (list view showing
AR balance) is grouped into US2 since the balance *column* only becomes visible once the list view
itself exists in US2, even though the balance *computation* is built in US3 — the list wires to it
in T034 below, matching plan.md's own note that this keeps US2 "independently testable" (name/VAT
columns render standalone; the balance column simply shows nothing meaningful until US3 lands, which
does not block US2's own acceptance scenarios). Almost all work lands inside the existing
`dodoo/addons/base` and `dodoo/addons/account` addons; no new addon.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US3; Setup / Foundational / Polish have no story label
- Paths are repository-relative. dodoo addons live under `dodoo/addons/`; tests under `tests/`.
- Per `[[accounting-test-isolation]]`: `tests/accounting/test_customer_database.py` reads AR totals
  across the shared test DB (like the pre-existing `test_account_balance.py`), so it must run
  standalone, not batched with other `tests/accounting/` files, in CI config.

---

## Phase 1: Setup

- [ ] T001 [P] File ADR docs from `plan.md`'s embedded ADR text: `docs/adr/046-customer-fields-base-account-split.md`,
  `docs/adr/047-ar-ledger-on-demand-computed-endpoint.md`,
  `docs/adr/048-bespoke-customer-views-unlink-guard.md` (title/status/context/decision/consequences
  + one-line threat note each, per Principle V)
- [ ] T002 [P] Confirm `pyproject.toml`'s ruff/pytest globs already cover the touched paths
  (`dodoo/addons/base`, `dodoo/addons/account`, `tests/accounting`) — no new addon, no config
  change expected; run `ruff check` as a sanity check

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user-story work begins until this phase is complete — every story needs the
schema columns and the shared test fixture created here.

- [ ] T003 [P] Add `street` (`Char(size=256)`), `city` (`Char(size=128)`), `state_id`
  (`Many2one("res.country.state")`), `zip` (`Char(size=32)`), `country_id`
  (`Many2one("res.country")`) fields to `ResPartner` in `dodoo/addons/base/models/res_partner.py`
  (ADR-046, data-model.md)
- [ ] T004 [P] Extend `_PARTNER_FK_COLUMNS` in `dodoo/addons/account/data/account_data.py` with
  `"ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS customer_rank INTEGER DEFAULT 0"` and
  `"ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_currency_id INTEGER"` (ADR-046,
  data-model.md)
- [ ] T005 [P] Add an `idx_account_move_line_partner_account` composite index
  `(partner_id, account_id)` on `account_move_line` to `dodoo/addons/account/data/indexes.py`'s
  `PERF_INDEXES` list, wired through the existing `ensure_indexes(env, ddl)` call (PERF-001/002)
- [ ] T006 [P] Add a `customer_id` fixture to `tests/accounting/conftest.py` (extends the existing
  `partner_id` fixture: `customer_rank=1`, `street`/`city`/`zip`/`country_id` set,
  `property_payment_term_id` set) for use by all three stories' tests
- [ ] T007 Extend `tests/accounting/test_migrations.py`: assert `res_partner.street`/`city`/
  `state_id`/`zip`/`country_id`/`customer_rank`/`property_currency_id` all exist after `account`
  module install (depends on T003, T004)

**Checkpoint**: schema ready — `res_partner` carries every column this feature needs; all three
user stories can now proceed.

---

## Phase 3: User Story 1 — Maintain the customer master list (Priority: P1) 🎯 MVP

**Goal**: An accountant can create, edit, archive, and (when no financial history exists) delete a
customer record with name, contact info, billing address, VAT number, default payment terms, and
default currency.

**Independent Test**: quickstart.md §1 — create a fully-populated customer, edit it, confirm a
missing-name create is rejected, confirm archive hides it from the default list while its AR
ledger stays reachable, confirm delete is blocked once it has a posted invoice.

### Tests for User Story 1

- [ ] T008 [P] [US1] Integration test: `POST /account/partner` with all fields → `201`-equivalent
  result, `customer_rank == 1`, fields persist on read-back (FR-001/007), in
  `tests/accounting/test_customer_database.py`
- [ ] T009 [P] [US1] Integration test: `PATCH /account/partner/{id}` updates a field, confirmed on
  read-back (FR-002), in `tests/accounting/test_customer_database.py`
- [ ] T010 [P] [US1] Integration test: `POST /account/partner` with no `name` → `400` naming the
  missing field (FR-001), in `tests/accounting/test_customer_database.py`
- [ ] T011 [P] [US1] Integration test: `write(active=False)` hides the customer from
  `search_read`'s default active-only domain but a direct `read` by id and its AR ledger still work
  (FR-005), in `tests/accounting/test_customer_database.py`
- [ ] T012 [P] [US1] Integration test: `unlink` on a customer with a posted invoice/payment raises
  `DodooError`; `unlink` on a customer with no financial history succeeds (FR-006), in
  `tests/accounting/test_customer_database.py`

### Implementation for User Story 1

- [ ] T013 [US1] Add `CustomerCreate`/`CustomerUpdate` Pydantic models to
  `dodoo/addons/account/validators.py`: `extra="forbid"`, `name` required on `CustomerCreate`
  (optional on `CustomerUpdate`), `email` checked by a stdlib-`re` `field_validator` (no `EmailStr`
  — Technical Context, research.md) (SEC-001, FR-001/013, contracts/customer-database.md) (depends
  on T008–T012 existing as failing tests)
- [ ] T014 [US1] Add a `ResPartner.create`/`write` classmethod override in
  `dodoo/addons/base/models/res_partner.py` enforcing non-empty `name` regardless of entry path
  (generic `execute_kw` or the dedicated routes below), matching the existing "override
  create/write, validate, call super()" pattern (FR-001) (depends on T013)
- [ ] T015 [US1] Add a `ResPartner.unlink` classmethod override in
  `dodoo/addons/base/models/res_partner.py`: reject deletion (raise `DodooError`, same message
  shape as `AccountMove.unlink`) when any id is referenced by `account_move.partner_id` or
  `account_payment.partner_id`; otherwise delegate to `super().unlink()` (FR-006, ADR-048) (depends
  on T014)
- [ ] T016 [US1] Add `POST /account/partner` and `PATCH /account/partner/{partner_id}` routes to
  `dodoo/addons/account/http/__init__.py` using `CustomerCreate`/`CustomerUpdate`; set
  `customer_rank=1` on create; structured `_log.info(...)` on create/write/unlink
  (`extra={"model": "res.partner", "record_id": ..., "event": ...}`, Principle IX) (depends on
  T013, T014, T015)
- [ ] T017 [US1] Create `dodoo/addons/account/static/views/customer-form.js`: field inputs for
  `name`/`email`/`phone`/`street`/`city`/`state_id`/`zip`/`country_id`/`vat`/
  `property_payment_term_id`/`property_currency_id`, Save/Discard/Delete/Archive actions calling
  the routes above, non-color-only validation errors (ADR-048) (depends on T016)
- [ ] T018 [US1] Register `#/accounting/customer/(new|\d+)` → `customer-form.js` in
  `dodoo/addons/web/static/app.js`'s `_ROUTES`, ahead of the generic
  `#/accounting/model/([^/]+)` patterns (ADR-048) (depends on T017)
- [ ] T019 [US1] Add a "Customers" item (`hash: '#/accounting/customers'`) to the existing
  "Customers" section in `dodoo/addons/account/static/account-menu.js`
- [ ] T020 [US1] Add new UI strings (customer form field labels, archive action, delete-blocked
  message) to `dodoo/addons/account/data/i18n/{en,ar}.json` per `[[i18n-per-addon-catalogs]]`

**Checkpoint**: customers can be created, edited, archived, and delete-guarded, independently of
search and the AR-ledger panel.

---

## Phase 4: User Story 2 — Find a customer quickly (Priority: P2)

**Goal**: An accountant can search/filter the customer list by name or VAT number.

**Independent Test**: quickstart.md §2 — create customers with distinct names/VAT numbers, search
by partial name, search by exact VAT, search with no matches.

### Tests for User Story 2

- [ ] T021 [P] [US2] Integration test: partial-name search returns only matching customers
  (FR-004), in `tests/accounting/test_customer_database.py`
- [ ] T022 [P] [US2] Integration test: exact-VAT search returns the matching customer (FR-004), in
  `tests/accounting/test_customer_database.py`
- [ ] T023 [P] [US2] Integration test: a search matching nothing returns an empty result, not an
  error (Edge Cases), in `tests/accounting/test_customer_database.py`

### Implementation for User Story 2

- [ ] T024 [US2] Create `dodoo/addons/account/static/views/customer-list.js`: fetch `res.partner`
  rows with `customer_rank > 0` via `search_read`, client-side substring filter on `name`/`vat`
  (the `coa-list.js` pattern), New button, archived toggle, columns name/VAT/balance (balance
  column wired in US3, T034) (ADR-048, FR-003/004) (depends on T017 for row-click navigation
  target)
- [ ] T025 [US2] Register `#/accounting/customers` → `customer-list.js` in
  `dodoo/addons/web/static/app.js`'s `_ROUTES`, ahead of the generic
  `#/accounting/([^/]+)` fallback (depends on T024)
- [ ] T026 [US2] Add search-box and empty-state UI strings to
  `dodoo/addons/account/data/i18n/{en,ar}.json`

**Checkpoint**: the customer list is searchable and reachable from the menu.

---

## Phase 5: User Story 3 — Review a customer's Accounts Receivable position (Priority: P1)

**Goal**: From a customer's own record, an accountant sees the current outstanding AR balance and
the full posted invoice/credit-note/payment history that produced it, with drill-down to each
document.

**Independent Test**: quickstart.md §3 — post two invoices and a partial payment against a
customer, confirm the AR ledger's balance and per-line status; confirm a new customer shows a
zero balance and empty history; confirm a cancelled invoice is excluded from the balance but still
listed.

### Tests for User Story 3

- [ ] T027 [P] [US3] Integration test: two posted invoices + one partial payment → `balance` and
  each line's `status` are correct (FR-008/009), in `tests/accounting/test_customer_database.py`
- [ ] T028 [P] [US3] Integration test: brand-new customer → `{"balance": "0.00", "lines": []}`, not
  an error (FR-008, Edge Cases), in `tests/accounting/test_customer_database.py`
- [ ] T029 [P] [US3] Integration test: a cancelled/voided invoice is excluded from `balance` but
  still appears with `status: "cancelled"` (FR-012, Edge Cases), in
  `tests/accounting/test_customer_database.py`

### Implementation for User Story 3

- [ ] T030 [US3] Create `dodoo/addons/account/models/account_partner.py`: module-level
  `async def get_ar_ledger(env, partner_id)` — unions posted `out_invoice`/`out_refund`/
  `out_receipt` move lines hitting an `asset_receivable`-type account with `account_payment` rows
  for the partner into one chronological list, computes each line's paid/partial/open/cancelled
  `status` from the line's existing `amount_residual`, sums open lines for `balance`, in
  `property_currency_id` (falling back to `res_company.currency_id`) (ADR-047, data-model.md)
  (depends on T003, T004, T006)
- [ ] T031 [US3] Register the new `account_partner` module in
  `dodoo/addons/account/models/__init__.py` (depends on T030)
- [ ] T032 [US3] Add `GET /account/partner/{partner_id}/ar-ledger` to
  `dodoo/addons/account/http/__init__.py`, `400 DodooError` for an unknown `partner_id`, structured
  `_log.info(...)` on read (Principle IX) (depends on T030, T031)
- [ ] T033 [US3] Extend `customer-form.js` with a read-only AR-ledger panel (date/reference/amount/
  status table) calling the new route; each row links to `#/accounting/move/{move_id}` (ADR-047/048,
  FR-009/010) (depends on T017, T032)
- [ ] T034 [US3] Wire `customer-list.js`'s balance column to the `ar-ledger` endpoint, fetched once
  per visible page rather than per keystroke (contracts/customer-database.md's behavior note)
  (depends on T024, T032)
- [ ] T035 [US3] Add AR-ledger UI strings (paid/partial/open/cancelled status labels, panel
  heading) to `dodoo/addons/account/data/i18n/{en,ar}.json`

**Checkpoint**: all three user stories are independently functional — the customer database
feature is complete end to end.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T036 [P] Extend `tests/benchmarks/test_accounting_perf.py`: PERF-001 (10,000 customers,
  list-fetch + client-side filter stays interactive), PERF-002 (5,000 AR-ledger lines for one
  customer, `GET .../ar-ledger` < 1s) (depends on T024, T030)
- [ ] T037 Re-run `tests/benchmarks/test_accounting_perf.py`'s existing invoice/payment posting
  benchmarks; confirm no regression, since the AR balance is never written at posting time
  (PERF-003) (depends on T036)
- [ ] T038 [P] Extend `tests/e2e/test_web_ui_a11y.py` for the customer list and form (including the
  AR-ledger panel): zero WCAG 2.1 AA contrast violations, full keyboard navigation, no color-only
  validation/status indicators (ACC-001…003) (depends on T017, T024, T033)
- [ ] T039 Run the project's i18n coverage check against the new customer screens' strings, per
  `[[i18n-per-addon-catalogs]]` — confirm Arabic mode shows no English fallback text (depends on
  T020, T026, T035)
- [ ] T040 Security hardening pass: confirm SEC-001…004 — `CustomerCreate`/`CustomerUpdate`'s
  `extra="forbid"` boundary rejects unexpected fields, every new route requires `auth="session"`,
  `get_ar_ledger` and the customer search use parameterized SQL only (no string-interpolated user
  input) (Principle III) (depends on T013, T016, T030, T032)
- [ ] T041 [P] Documentation: verify `docs/adr/046…048-*.md` (T001) accurately reflect the final
  implementation (Principle V)
- [ ] T042 Run `quickstart.md` end to end against a fresh install; confirm every numbered scenario
  passes (depends on T001–T041)
- [ ] T043 Run the full pre-existing `tests/accounting/` suite unchanged; confirm 100% pass (no
  regression) (depends on T042)
- [ ] T044 Observability review (Principle IX): confirm customer `create`/`write`/`unlink` and the
  AR-ledger read each emit a structured `_log.info(...)` entry matching the existing
  `extra={"model": ..., "record_id": ..., "event": ...}` convention; add any missing call sites
  (depends on T016, T032)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories (creates every
  schema column and the shared `customer_id` test fixture every story needs).
- **User Stories (Phase 3–5)**: All depend on Foundational completion.
  - US1 (P1) has no dependency on US2/US3 and is the MVP — a usable customer directory on its own.
  - US2 (P2) depends on US1/T017 only for its row-click navigation target (`customer-form.js`
    existing); its own search/list logic is independent.
  - US3 (P1) depends on US1/T017 (the form to attach its AR-ledger panel to) and, for its list
    column (T034), on US2/T024 — but US3's core deliverable (`get_ar_ledger` + the route + the
    form panel, T030–T033) is independently testable via the API alone before US2 lands, per
    quickstart.md §3.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- Tests are written before implementation (and must fail first).
- Schema/model changes before the routes that expose them; routes before the static views that
  call them.
- Story complete before moving to the next priority.

### Parallel Opportunities

- T001–T002 (Setup) can run in parallel.
- T003–T006 (Foundational) can run in parallel (different files); T007 depends on T003/T004.
- All US1 tests (T008–T012) can run in parallel.
- All US2 tests (T021–T023) and all US3 tests (T027–T029) can run in parallel within their story.
- T036 and T038 (Polish) can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Integration test: create customer with all fields in tests/accounting/test_customer_database.py"
Task: "Integration test: edit customer in tests/accounting/test_customer_database.py"
Task: "Integration test: missing-name create rejected in tests/accounting/test_customer_database.py"
Task: "Integration test: archive hides from default list in tests/accounting/test_customer_database.py"
Task: "Integration test: delete blocked when referenced in tests/accounting/test_customer_database.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: quickstart.md §1 passes independently
5. Deploy/demo if ready — a usable customer directory, even before search or the AR ledger exist

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 3 (AR ledger) → Test independently → Deploy/Demo — the feature's distinguishing
   capability, and P1 alongside US1
4. Add User Story 2 (search) → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- Verify tests fail before implementing.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.
