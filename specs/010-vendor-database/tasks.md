---

description: "Task list for Vendor Database implementation"
---

# Tasks: Vendor Database

**Input**: Design documents from `specs/010-vendor-database/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the constitution requires ≥80% unit / 100% critical-path branch coverage, and
this feature's own success criteria (SC-004, SC-005) are only verifiable with test coverage of the
AP-balance computation and the CRUD/archive/delete-guard paths, matching 009-customer-database's
own precedent.

**Organization**: Tasks are grouped by the three user stories from spec.md, in priority order
(P1: US1, US3; P2: US2). FR-to-story mapping (all 15 FRs, each assigned once): US1={FR-001,002,005,
006,007,011,013,014,015}, US2={FR-003,004}, US3={FR-008,009,010,012}. Note: FR-003 (list view
showing AP balance) is grouped into US2 since the balance *column* only becomes visible once the
list view itself exists in US2, even though the balance *computation* is built in US3 — mirrors
009's own T037 pattern exactly (the list wires to it in T034 below). Almost all work lands inside
the existing `dodoo/addons/account` addon; no changes to `base`, no new addon.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US3; Setup / Foundational / Polish have no story label
- Paths are repository-relative. dodoo addons live under `dodoo/addons/`; tests under `tests/`.
- Per `[[accounting-test-isolation]]`: `tests/accounting/test_vendor_database.py` reads AP totals
  across the shared test DB (like the pre-existing `test_customer_database.py`), so it must run
  standalone, not batched with other `tests/accounting/` files, in CI config.

---

## Phase 1: Setup

- [ ] T001 [P] File ADR docs from `plan.md`'s embedded ADR text: `docs/adr/049-supplier-rank-cross-addon-column.md`,
  `docs/adr/050-ap-ledger-on-demand-computed-endpoint.md`,
  `docs/adr/051-bespoke-vendor-views-dedicated-create-update-routes.md` (title/status/context/decision/consequences
  + one-line threat note each, per Principle V)
- [ ] T002 [P] Confirm `pyproject.toml`'s ruff/pytest globs already cover the touched paths
  (`dodoo/addons/account`, `tests/accounting`) — no new addon, no config change expected; run
  `ruff check` as a sanity check

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user-story work begins until this phase is complete — every story needs the
schema column, the write path for the raw `account`-owned columns, and the shared test fixture
created here.

- [ ] T003 [P] Extend `_PARTNER_FK_COLUMNS` in `dodoo/addons/account/data/account_data.py` with
  `"ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS supplier_rank INTEGER DEFAULT 0"`, appended
  after the existing `customer_rank`/`property_currency_id` entries without modifying them
  (ADR-049, data-model.md)
- [ ] T004 [P] Extend `_PROPERTY_COLUMNS` in `dodoo/addons/account/models/account_partner.py`'s
  `write_partner_properties` with `"supplier_rank"` and `"property_supplier_payment_term_id"`
  alongside its existing three entries, so the vendor create/update routes (US1) can persist them
  (data-model.md)
- [ ] T005 Extend `tests/accounting/test_migrations.py`'s `EXPECTED_COLUMNS` with
  `("res_partner", "supplier_rank")` (depends on T003)
- [ ] T006 [P] Add a `vendor_id` fixture to `tests/accounting/conftest.py` for use by all three
  stories' tests: `ResPartner.create` for the plain fields (`name`, `company_id`, `active`,
  `email`, `phone`, `street`, `city`, `zip`, `vat`) followed by `write_partner_properties(env,
  partner_id, {"supplier_rank": 1, "property_supplier_payment_term_id": payment_term_id,
  "property_currency_id": currency_id})` — the proven two-step shape `test_customer_database.py`
  already uses for its own ad hoc customer creation, **not** the existing `customer_id` fixture's
  direct-vals-into-`create` shape (those raw columns are silently dropped by the generic `create`
  path, per `account_partner.py`'s own module docstring) (depends on T003, T004)

**Checkpoint**: schema ready — `res_partner` carries `supplier_rank` and can persist every raw
column this feature needs; all three user stories can now proceed.

---

## Phase 3: User Story 1 — Maintain the vendor master list (Priority: P1) 🎯 MVP

**Goal**: An accountant can create, edit, archive, and (when no financial history exists) delete a
vendor record with name, contact info, billing address, VAT number, default payment terms, and
default currency; a partner can independently be a customer, a vendor, or both.

**Independent Test**: quickstart.md §1 — create a fully-populated vendor, edit it, confirm a
missing-name create is rejected, confirm archive hides it from the default list while its AP
ledger stays reachable, confirm delete is blocked once it has a posted bill.

### Tests for User Story 1

- [ ] T007 [P] [US1] Integration test: `POST /account/vendor` with all fields → result,
  `supplier_rank == 1`, fields persist on read-back (FR-001/007), in
  `tests/accounting/test_vendor_database.py`
- [ ] T008 [P] [US1] Integration test: `PATCH /account/vendor/{id}` updates a field, confirmed on
  read-back (FR-002), in `tests/accounting/test_vendor_database.py`
- [ ] T009 [P] [US1] Integration test: `POST /account/vendor` with no `name` → `400` naming the
  missing field (FR-001), in `tests/accounting/test_vendor_database.py`
- [ ] T010 [P] [US1] Integration test: `write(active=False)` hides the vendor from
  `GET /account/vendors`' default active-only response but a direct `GET /account/partner/{id}`
  and its AP ledger still work (FR-005), in `tests/accounting/test_vendor_database.py`
- [ ] T011 [P] [US1] Integration test: `unlink` on a vendor with a posted bill/payment raises
  `DodooError`; `unlink` on a vendor with no financial history succeeds (FR-006, the existing 009
  guard), in `tests/accounting/test_vendor_database.py`
- [ ] T012 [P] [US1] Integration test: `POST /account/vendor` with no `property_currency_id`/
  `property_supplier_payment_term_id` → both persist as `NULL` (defer-to-company-default); a
  subsequent `PATCH` setting either explicitly persists the override (FR-011), in
  `tests/accounting/test_vendor_database.py`
- [ ] T013 [P] [US1] Integration test: creating a second vendor with a `vat` already used by an
  existing active vendor succeeds (no hard block) — duplicate-VAT is UI-side advisory only, not a
  server-side rejection (Edge Cases), in `tests/accounting/test_vendor_database.py`
- [ ] T014 [P] [US1] Integration test: build an ad hoc customer partner inline
  (`ResPartner.create` + `write_partner_properties(..., {"customer_rank": 1})` — **not** the
  existing `customer_id` fixture, which silently fails to persist `customer_rank`/
  `property_payment_term_id`/`property_currency_id` since `BaseModel.create` filters `vals` to
  `k in cls._fields` and none of those three are declared `Field`s on `ResPartner`; a pre-existing
  009 fixture bug no current test happens to exercise — confirmed by reading
  `dodoo/core/models.py::BaseModel.create` and `tests/accounting/conftest.py:177-199` directly),
  then `PATCH` it via `/account/vendor/{id}` with `supplier_rank: 1` → the same partner id now
  satisfies both roles, appears in both `GET /account/customers` and `GET /account/vendors`, with
  independent, correctly-scoped `ar-ledger`/`ap-ledger` responses (FR-014/015, Edge Cases
  dual-role), in `tests/accounting/test_vendor_database.py`

### Implementation for User Story 1

- [ ] T015 [US1] Add `VendorCreate`/`VendorUpdate` Pydantic models to
  `dodoo/addons/account/validators.py`: `extra="forbid"`, `name` required on `VendorCreate`
  (optional on `VendorUpdate`), `email` validated by reusing `CustomerCreate`'s existing `_EMAIL_RE`
  pattern (no new regex, no new dependency) (SEC-001, FR-001/013, contracts/vendor-database.md)
  (depends on T007–T014 existing as failing tests)
- [ ] T016 [US1] Add `POST /account/vendor` and `PATCH /account/vendor/{partner_id}` routes to
  `dodoo/addons/account/http/__init__.py` using `VendorCreate`/`VendorUpdate`; set
  `supplier_rank=1` on create via `write_partner_properties`; structured `_log.info(...)` on
  create/write (`extra={"model": "res.partner", "record_id": ..., "event": ...}`, Principle IX)
  (depends on T015, T004)
- [ ] T017 [US1] Create `dodoo/addons/account/static/views/vendor-form.js`: field inputs for
  `name`/`email`/`phone`/`street`/`city`/`state_id`/`zip`/`country_id`/`vat`/
  `property_supplier_payment_term_id`/`property_currency_id`, Save/Discard/Delete/Archive actions
  calling the routes above, non-color-only validation errors; before save, if `vat` is set, a
  `search_read` for another active partner with the same `vat` shows a non-blocking warning banner
  (save still proceeds) — a file-for-file mirror of `customer-form.js` (ADR-051, Edge Cases)
  (depends on T016)
- [ ] T018 [US1] Register `#/accounting/vendor/(new|\d+)` → `vendor-form.js` in
  `dodoo/addons/web/static/app.js`'s `_ROUTES`, immediately after the existing customer routes and
  ahead of the generic `#/accounting/([^/]+)` catch-all; add the vendor id-parsing branches to
  `_paramsFromHash` (ADR-051) (depends on T017)
- [ ] T019 [US1] Add a "Vendors" item (`hash: '#/accounting/vendors'`) to the existing "Vendors"
  section in `dodoo/addons/account/static/account-menu.js`, alongside its existing Bills/Credit
  Notes/Payments items
- [ ] T020 [US1] Add new UI strings (vendor form field labels, archive action, delete-blocked
  message, duplicate-VAT warning) to `dodoo/addons/account/data/i18n/{en,ar}.json` per
  `[[i18n-per-addon-catalogs]]`

**Checkpoint**: vendors can be created, edited, archived, and delete-guarded, independently of
search and the AP-ledger panel. A partner can also be promoted to a vendor from an existing
customer record.

---

## Phase 4: User Story 2 — Find a vendor quickly (Priority: P2)

**Goal**: An accountant can search/filter the vendor list by name or VAT number.

**Independent Test**: quickstart.md §2 — create vendors with distinct names/VAT numbers, search by
partial name, search by exact VAT, search with no matches.

### Tests for User Story 2

- [ ] T021 [P] [US2] Integration test: partial-name search returns only matching vendors (FR-004),
  in `tests/accounting/test_vendor_database.py`
- [ ] T022 [P] [US2] Integration test: exact-VAT search returns the matching vendor (FR-004), in
  `tests/accounting/test_vendor_database.py`
- [ ] T023 [P] [US2] Integration test: a search matching nothing returns an empty result, not an
  error (Edge Cases), in `tests/accounting/test_vendor_database.py`

### Implementation for User Story 2

- [ ] T024 [US2] Add `GET /account/vendors` route to `dodoo/addons/account/http/__init__.py`
  (`list_vendors`, mirroring `list_customers`'s raw-SQL shape for `supplier_rank > 0`, since it's
  an undeclared column — contracts/vendor-database.md correction) and create
  `dodoo/addons/account/static/views/vendor-list.js`: fetch vendors via that route, client-side
  substring filter on `name`/`vat` (the `customer-list.js` pattern), New button, archived toggle,
  columns name/VAT/balance (balance column wired in US3, T034) (ADR-051, FR-003/004) (depends on
  T017 for row-click navigation target)
- [ ] T025 [US2] Register `#/accounting/vendors` → `vendor-list.js` in
  `dodoo/addons/web/static/app.js`'s `_ROUTES`, ahead of the generic `#/accounting/([^/]+)$`
  catch-all (depends on T024)
- [ ] T026 [US2] Add search-box and empty-state UI strings to
  `dodoo/addons/account/data/i18n/{en,ar}.json`

**Checkpoint**: the vendor list is searchable and reachable from the menu.

---

## Phase 5: User Story 3 — Review a vendor's Accounts Payable position (Priority: P1)

**Goal**: From a vendor's own record, an accountant sees the current outstanding AP balance and
the full posted bill/credit-note/payment history that produced it, with drill-down to each
document.

**Independent Test**: quickstart.md §3 — post two bills and a partial payment against a vendor,
confirm the AP ledger's balance and per-line status; confirm a new vendor shows a zero balance and
empty history; confirm a cancelled bill is excluded from the balance but still listed.

### Tests for User Story 3

- [ ] T027 [P] [US3] Integration test: two posted bills + one partial payment → `balance` and each
  line's `status` are correct (FR-008/009), in `tests/accounting/test_vendor_database.py`
- [ ] T028 [P] [US3] Integration test: brand-new vendor → `{"balance": "0.00", "lines": []}`, not
  an error (FR-008, Edge Cases), in `tests/accounting/test_vendor_database.py`
- [ ] T029 [P] [US3] Integration test: a cancelled bill is excluded from `balance` but still
  appears with `status: "cancelled"` (FR-012, Edge Cases), in
  `tests/accounting/test_vendor_database.py`
- [ ] T030 [P] [US3] Unit test (no DB): feed `_status_and_balance(lines)` a fixed list of
  bill/credit_note/payment/cancellation fixture dicts (AP-labeled `type` values) and confirm
  balance summation and per-line paid/partial/open/cancelled classification match the same
  behavior already proven for AR-labeled input in `test_customer_database.py` — confirms the
  reused helper is genuinely type-agnostic (research.md D5, Principle II), in
  `tests/accounting/test_vendor_database.py`

### Implementation for User Story 3

- [ ] T031 [US3] Add `get_ap_ledger(env, partner_id)` to
  `dodoo/addons/account/models/account_partner.py`, alongside the existing `get_ar_ledger`: unions
  posted `in_invoice`/`in_refund`/`in_receipt` move lines hitting a `liability_payable`-type
  account with `account_payment` rows where `partner_type = 'supplier'` for the partner into one
  chronological list of plain dicts, then passes that list to the **existing, unmodified**
  `_status_and_balance(lines)` function — no AP-specific variant — in the partner's
  `property_currency_id` (falling back to `res_company.currency_id`) (ADR-050, data-model.md)
  (depends on T003)
- [ ] T032 [US3] Add `GET /account/partner/{partner_id}/ap-ledger` to
  `dodoo/addons/account/http/__init__.py`, `400 DodooError` for an unknown `partner_id`, structured
  `_log.info(...)` on read (Principle IX); extend the existing `read_customer` handler's `SELECT`
  to also return `supplier_rank`/`property_supplier_payment_term_id` (ADR-049) (depends on T031)
- [ ] T033 [US3] Extend `vendor-form.js` with a read-only Accounts Payable panel (date/reference/
  amount/status table, "Bill" type label in place of "Invoice") calling the new route; each row
  links to `#/accounting/move/{move_id}` (ADR-050/051, FR-009/010) (depends on T017, T032)
- [ ] T034 [US3] Wire `vendor-list.js`'s balance column to the `ap-ledger` endpoint, fetched once
  per visible page rather than per keystroke (contracts/vendor-database.md's behavior note)
  (depends on T024, T032)
- [ ] T035 [US3] Add AP-ledger UI strings ("Bill" type label, "Accounts Payable" panel heading,
  empty-state message) to `dodoo/addons/account/data/i18n/{en,ar}.json`

**Checkpoint**: all three user stories are independently functional — the vendor database feature
is complete end to end.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T036 [P] Extend `tests/benchmarks/test_accounting_perf.py`: PERF-001 (10,000 vendors,
  list-fetch + client-side filter stays interactive), PERF-002 (5,000 AP-ledger lines for one
  vendor, `GET .../ap-ledger` < 1s) — this also empirically confirms 009's existing indexes are
  sufficient with zero new ones added (research.md D6) (depends on T024, T031)
- [ ] T037 Re-run `tests/benchmarks/test_accounting_perf.py`'s existing invoice/payment **and**
  bill/payment posting benchmarks; confirm no regression, since the AP balance is never written at
  posting time (PERF-003) (depends on T036)
- [ ] T038 [P] Extend `tests/e2e/test_web_ui_a11y.py` for the vendor list and form (including the
  AP-ledger panel): zero WCAG 2.1 AA contrast violations, full keyboard navigation, no color-only
  validation/status indicators (ACC-001…003) (depends on T017, T024, T033)
- [ ] T039 Run the project's i18n coverage check against the new vendor screens' strings, per
  `[[i18n-per-addon-catalogs]]` — confirm Arabic mode shows no English fallback text (depends on
  T020, T026, T035)
- [ ] T040 Security hardening pass: confirm SEC-001…004 — `VendorCreate`/`VendorUpdate`'s
  `extra="forbid"` boundary rejects unexpected fields, every new route requires `auth="session"`,
  `get_ap_ledger` and the vendor search use parameterized SQL only (no string-interpolated user
  input) (Principle III) (depends on T015, T016, T024, T031, T032)
- [ ] T041 [P] Documentation: verify `docs/adr/049…051-*.md` (T001) accurately reflect the final
  implementation, including the `get_ap_ledger`/reused-`_status_and_balance` split (Principle V)
- [ ] T042 Run `quickstart.md` end to end against a fresh install; confirm every numbered scenario
  passes, including §4's dual customer/vendor-role check (depends on T001–T041)
- [ ] T043 Run the full pre-existing `tests/accounting/` suite unchanged (including
  `test_customer_database.py`); confirm 100% pass — no regression from touching the shared
  `account_partner.py`/`http/__init__.py`/`account_data.py` files (depends on T042)
- [ ] T044 Observability review (Principle IX): confirm vendor `create`/`write`/`unlink` and the
  AP-ledger read each emit a structured `_log.info(...)` entry matching the existing
  `extra={"model": ..., "record_id": ..., "event": ...}` convention; add any missing call sites
  (depends on T016, T032)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories (creates the
  schema column, the write path for raw columns, and the shared `vendor_id` test fixture every
  story needs).
- **User Stories (Phase 3–5)**: All depend on Foundational completion.
  - US1 (P1) has no dependency on US2/US3 and is the MVP — a usable vendor directory on its own.
  - US2 (P2) depends on US1/T017 only for its row-click navigation target (`vendor-form.js`
    existing); its own search/list logic is independent.
  - US3 (P1) depends on US1/T017 (the form to attach its AP-ledger panel to) and, for its list
    column (T034), on US2/T024 — but US3's core deliverable (`get_ap_ledger` + the route + the
    form panel, T031–T033) is independently testable via the API alone before US2 lands, per
    quickstart.md §3.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- Tests are written before implementation (and must fail first).
- Schema/model changes before the routes that expose them; routes before the static views that
  call them.
- Story complete before moving to the next priority.

### Parallel Opportunities

- T001–T002 (Setup) can run in parallel.
- T003, T004, T006 (Foundational) can run in parallel (different files); T005 depends on T003.
- All US1 tests (T007–T014) can run in parallel.
- All US2 tests (T021–T023) and all US3 tests (T027–T030) can run in parallel within their story.
- T036 and T038 (Polish) can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Integration test: create vendor with all fields in tests/accounting/test_vendor_database.py"
Task: "Integration test: edit vendor in tests/accounting/test_vendor_database.py"
Task: "Integration test: missing-name create rejected in tests/accounting/test_vendor_database.py"
Task: "Integration test: archive hides from default list in tests/accounting/test_vendor_database.py"
Task: "Integration test: delete blocked when referenced in tests/accounting/test_vendor_database.py"
Task: "Integration test: currency/term default-then-override in tests/accounting/test_vendor_database.py"
Task: "Integration test: duplicate VAT is not hard-blocked in tests/accounting/test_vendor_database.py"
Task: "Integration test: existing customer promoted to also be a vendor in tests/accounting/test_vendor_database.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: quickstart.md §1 passes independently
5. Deploy/demo if ready — a usable vendor directory, even before search or the AP ledger exist

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 3 (AP ledger) → Test independently → Deploy/Demo — the feature's distinguishing
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
