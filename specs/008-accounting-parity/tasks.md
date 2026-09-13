---

description: "Task list for Accounting Parity with Odoo 19 Community implementation"
---

# Tasks: Accounting Parity with Odoo 19 Community

**Input**: Design documents from `specs/008-accounting-parity/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the constitution requires ≥ 80% unit / 100% critical-path branch coverage,
and this feature's own success criteria (SC-002, SC-005, SC-006, SC-007) are only verifiable with
test coverage of every FR.

**Organization**: Tasks are grouped by the six user stories from spec.md, in priority order
(P1: US1, US2; P2: US3, US4; P3: US5, US6). Almost all work lands inside the existing
`dodoo/addons/account` addon; the new `dodoo/addons/analytic/` addon and `base`'s
`res.currency.rate` model are built out in Setup/Foundational since multiple stories depend on
them. FR-to-story mapping (all 39 FRs, each assigned once): US1={FR-010,013,014,015,017,018,019},
US2={FR-020…030}, US3={FR-001,002,003,004,005,006,007,008,009,031,032,033}, US4={FR-016,034,035,
036,037}, US5={FR-011,012}, US6={FR-038,039} — FR-001/002 (chart-of-accounts) and FR-031…033
(lock dates) are grouped into US3 per `plan.md`'s contract-to-story mapping (both are integrity/
audit-trail concerns, `coa-journals-audit-trail.md` / `bank-cash.md`), and FR-016 (tax grids/tax
report) is grouped into US4 since the Tax Report itself is a reporting deliverable, per spec.md's
own acceptance-scenario citations.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6; Setup / Foundational / Polish have no story label
- Paths are repository-relative. dodoo addons live under `dodoo/addons/`; tests under `tests/`.
- Per `[[accounting-test-isolation]]`: `tests/accounting/test_reports_opening_balance.py` and
  `tests/accounting/test_tax_report.py` must run standalone, not batched with other
  `tests/accounting/` files, exactly like the pre-existing `test_reports.py`/`test_account_balance.py`.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create `dodoo/addons/analytic/` skeleton: `__init__.py` (imports `http`, `models`),
  `__manifest__.py` (`{"name": "Analytic Accounting", "version": "1.0.0", "depends": ["base", "web"],
  "application": False}`), empty `models/__init__.py`, `http/__init__.py`, `data/__init__.py`
  (ADR-045)
- [X] T002 Add `"analytic"` to `dodoo/addons/account/__manifest__.py`'s `depends` list (ADR-045,
  confirmed against `../odoo-19.0/addons/account/__manifest__.py`'s own `depends`)
- [X] T003 [P] Create `tests/analytic/__init__.py` and `tests/analytic/conftest.py` mirroring
  `tests/accounting/conftest.py`'s fixtures (`pg_container`, `db_url`, `modules_installed` installing
  `"analytic"`, `env`, `company_id`)
- [X] T004 [P] Confirm `pyproject.toml`'s ruff/pytest globs already cover
  `dodoo/addons/analytic` and `tests/analytic` (no change expected); run `ruff check` on the new
  addon skeleton
- [X] T005 [P] File ADR docs from `plan.md`'s embedded ADR text: `docs/adr/037-coa-group-classification-and-reconcile-constraints.md`,
  `038-per-journal-sequencing-cancel-state-reversal-review.md`,
  `039-hash-chain-line-immutability-lock-dates.md`,
  `040-discount-price-included-tax-rounding-debit-note-downpayment.md`,
  `041-payment-term-validation-early-discount-due-date-fix.md`,
  `042-reconciliation-writeoff-suggestions-multicurrency-fx.md`,
  `043-bank-statements-continuity-cash-rounding.md`,
  `044-report-opening-balance-drilldown-aged-bucket-fiscal-year.md`,
  `045-analytic-accounting-addon.md` (title/status/context/decision/consequences + one-line threat
  note each, per Principle V)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user-story work begins until this phase is complete — `account` gains its
first security/validators framework here, and both new stand-alone models (`analytic.account`,
`res.currency.rate`) that later stories reference are created here.

- [X] T006 Create `dodoo/addons/account/security.py`: `GROUP_USER = "Accounting User"`,
  `GROUP_MANAGER = "Accounting Manager"`, `seed_groups(env)`, `assign_accounting_group(env, uid,
  level)` — `account`'s first group concept (research.md D8; mirrors `hr/security.py`'s two-level
  nesting pattern)
- [X] T007 Create `dodoo/addons/account/validators.py`: `Payload` base (Pydantic v2,
  `extra="forbid"`), `validate(model_cls, payload)`, `group_names(env, uid)`, `is_member(env, uid,
  name)`, `require_groups(env, uid, *names)` — `account`'s first validators file (canonical copy per
  `hr/validators.py`)
- [X] T008 Create `dodoo/addons/account/data/groups.py` (`seed_groups()` calling
  `security.seed_groups`); wire it into `dodoo/addons/account/data/account_data.py::seed_account_data`'s
  orchestrator (depends on T006)
- [X] T009 [P] Create `dodoo/addons/analytic/models/analytic_plan.py`: `AnalyticPlan` (`name`,
  `parent_id` [Many2one self], `company_id`) (data-model.md)
- [X] T010 [P] Create `dodoo/addons/analytic/models/analytic_account.py`: `AnalyticAccount` (`name`,
  `code`, `plan_id`, `company_id`, `active`) (data-model.md)
- [X] T011 Create `dodoo/addons/analytic/data/ir_model_sync.py` (`sync_ir_model`, own copy per
  addon convention); wire from `analytic/__init__.py::post_install` (depends on T009, T010)
- [X] T012 [P] Create `dodoo/addons/analytic/validators.py`: `AnalyticPlanCreate`,
  `AnalyticAccountCreate` (contracts/reports-analytic.md)
- [X] T013 [P] Create `dodoo/addons/analytic/http/__init__.py` skeleton (static mount + `json_ok`/
  `json_err` helpers; CRUD stays generic JSON-RPC dispatch — no dedicated REST routes needed)
- [X] T014 Add `ResCurrencyRate` model (`currency_id`, `rate_date`, `rate`, manual entry only per
  spec Clarifications) and `get_rate(env, currency_id, company_currency_id, date)` (latest
  `rate_date <= date`) to `dodoo/addons/base/models/res_currency.py`, alongside the existing
  `ResCurrency` (FR-023, research.md D4)
- [X] T015 Create `dodoo/addons/account/models/account_account_tag.py`: `AccountAccountTag`
  (`name`, `applicability` [Selection, default `"taxes"`], `country_id`) — foundational for both
  US1's tax-grid tagging and US4's Tax Report (data-model.md)
- [X] T016 Add `_COMPANY_LOCK_COLUMNS` (`fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`,
  `purchase_lock_date`, all `DATE`), `_COMPANY_EXCHANGE_COLUMNS`
  (`income_currency_exchange_account_id`, `expense_currency_exchange_account_id`, both `INTEGER`
  referencing `account_account`), and `_COMPANY_FISCAL_YEAR_COLUMNS` (`fiscalyear_last_month`
  default `12`, `fiscalyear_last_day` default `31`) `ALTER TABLE res_company ADD COLUMN IF NOT
  EXISTS ...` lists to `dodoo/addons/account/data/account_data.py`, run inside
  `seed_account_data` alongside the existing `_PARTNER_FK_COLUMNS` (research.md D5) — needed by
  US2 (exchange columns), US3 (lock dates), US4 (fiscal-year columns)
- [X] T017 Add a `CREATE EXTENSION IF NOT EXISTS pg_trgm` statement to
  `dodoo/addons/account/data/account_data.py`'s `seed_account_data` (needed by US2's
  `suggest_matches` trigram similarity ranking, ADR-042)
- [X] T018 [P] Test `tests/accounting/test_migrations.py` (NEW) asserting every new table/column
  introduced by this feature (per `data-model.md`) exists after `env.modules.install("analytic")`
  and an `account` upgrade — extended incrementally as each story below adds its own
  tables/columns

**Checkpoint**: `account` has its first security/validators framework; `analytic` addon installs
standalone; `res_currency_rate` and `account_account_tag` exist; `res_company` carries all 8 new
columns.

---

## Phase 3: User Story 1 — Correct invoice, tax, and payment-term figures (Priority: P1) 🎯 MVP

**Goal**: Invoice/bill line discounts, price-included tax, per-company rounding method, and
payment-term validation/early-discount all compute figures matching Odoo 19 Community.

**Independent Test**: quickstart.md §1 — a line with a 10% discount and a 15% tax, a
price-included variant of the same tax, a 40/30/30 payment term, and an early-payment-discount
term with an "end of month on the 15th, next month" due-date rule.

### Tests for User Story 1

- [X] T019 [P] [US1] Unit test discount-net `price_subtotal` derivation (FR-010/013) in
  `tests/accounting/test_invoice_discount_tax.py`
- [X] T020 [P] [US1] Unit test price-included tax extraction formula (FR-014) added to
  `tests/accounting/test_invoice_discount_tax.py`
- [X] T021 [P] [US1] Unit test `round_per_line` vs `round_globally` company rounding methods
  (FR-015) added to `tests/accounting/test_invoice_discount_tax.py`
- [X] T022 [P] [US1] Unit test payment-term 100%-sum constraint, `days_end_of_month_on_the` +
  `next_month` due-date fix, and early-discount `discount_date`/`discount_amount` computed keys
  (FR-017/018/019) in `tests/accounting/test_payment_terms.py`

### Implementation for User Story 1

- [X] T023 [US1] Add `discount` (`Monetary`, 0–100) field to `AccountMoveLine`; extend
  `_apply_price_defaults` in `dodoo/addons/account/models/account_move_line.py` to derive
  `price_subtotal = quantity × price_unit × (1 - discount/100)` (FR-010, ADR-040)
- [X] T024 [US1] Rewrite `AccountMove._compute_tax_lines` in
  `dodoo/addons/account/models/account_move.py`: use the discount-net `price_subtotal` as `base`;
  branch on each applicable tax's `price_include` (reverse-charge extraction when `True`); branch
  on `res_company.tax_rounding_method` for `round_per_line` (round each line's tax before summing)
  vs. the existing `round_globally` default (FR-013/014/015, ADR-040) (depends on T023)
- [X] T025 [US1] Add `tag_ids` `Many2many("account.account.tag",
  relation_table="account_tax_repartition_line_tag_rel", column1="repartition_line_id",
  column2="tag_id")` to `AccountTaxRepartitionLine` in
  `dodoo/addons/account/models/account_tax.py` (FR-016 groundwork — the Tax Report itself is built
  in US4) (depends on T015)
- [X] T026 [US1] Add `create`/`write` override on `AccountPaymentTermLine` in
  `dodoo/addons/account/models/account_payment_term.py`: for `value == "percent"` lines, re-sum the
  parent term's percent-type lines (including the one being written) and raise `DodooError` if the
  total ≠ 100 (FR-017, ADR-041)
- [X] T027 [US1] Add `next_month` (`Boolean`, default `False`) field to `AccountPaymentTermLine`;
  fix `_compute_due_date`'s `days_end_of_month_on_the` branch to resolve the target month (current,
  or next when `next_month=True`) before clamping the configured day within that month's length
  (FR-019, ADR-041) (depends on T026)
- [X] T028 [US1] Add `early_payment_discount_account_id` (`Many2one("account.account")`, nullable)
  to `AccountPaymentTerm`; extend `compute_installments` to also return `discount_date`
  (`invoice_date + discount_days`) and `discount_amount` (installment amount less
  `discount_percentage`) per installment when `early_discount` is `True` (FR-018, ADR-041) (depends
  on T027)
- [X] T029 [US1] Extend `POST /account/payment/{id}/register` in
  `dodoo/addons/account/http/__init__.py`: when the payment's date is on or before an
  installment's `discount_date`, reduce the reconciled amount by `discount_amount` and post the
  difference to `early_payment_discount_account_id` (FR-018) (depends on T028)
- [X] T030 [US1] Add `AccountTagCreate` (`name`, `applicability: Literal["taxes"] = "taxes"`,
  `country_id: int | None`) to `dodoo/addons/account/validators.py`; confirm `account.account.tag`
  and `account.tax.repartition.line.tag_ids` are reachable via the existing generic JSON-RPC
  `create`/`write` dispatch (FR-016 groundwork, no new REST route) (depends on T025, T007)
- [X] T031 [P] [US1] Update `dodoo/addons/account/static/views/invoice-form.js`: per-line discount
  input, a price-included indicator on the tax selector, and `discount_date`/`discount_amount`
  surfaced on the payment-term schedule display
- [X] T032 [US1] Update `dodoo/addons/account/data/i18n/{en,ar}.json` with new UI strings
  (discount, price-included, rounding method, early-payment discount) per
  `[[i18n-per-addon-catalogs]]`
- [X] T033 [US1] Extend `tests/accounting/test_migrations.py`: assert `account_move_line.discount`,
  the `account_tax_repartition_line_tag_rel` junction table, `account_payment_term_line.next_month`,
  and `account_payment_term.early_payment_discount_account_id` all exist (depends on T023, T025,
  T027, T028)

**Checkpoint**: invoices/bills compute discount-net, price-included, correctly-rounded tax;
payment terms validate their percentages and expose early-discount figures end to end.

---

## Phase 4: User Story 2 — Reliable reconciliation, multi-currency, and cash handling (Priority: P1)

**Goal**: Reconciliation supports write-offs and match suggestions and is currency-aware; foreign-
currency documents convert correctly and generate realized/unrealized FX entries; bank statements
exist and reconcile against them; cash payments round correctly.

**Independent Test**: quickstart.md §2 — a short payment reconciled with a write-off, ranked
reconciliation suggestions, a foreign-currency invoice/payment pair at different rates producing a
realized gain/loss, a period-end revaluation, a cash-rounded invoice, and two sequential bank
statements with a continuity check.

### Tests for User Story 2

- [X] T034 [P] [US2] Unit test `ResCurrencyRate.get_rate` (latest `rate_date <= date`) (FR-023) in
  `tests/accounting/test_multi_currency.py`
- [X] T035 [P] [US2] Unit test FX conversion at posting (`amount_currency × rate → debit/credit`)
  added to `tests/accounting/test_multi_currency.py`
- [X] T036 [P] [US2] Integration test reconciliation write-off posting + currency-aware partial
  reconcile (`debit_amount_currency`/`credit_amount_currency`) in
  `tests/accounting/test_reconciliation_writeoff.py`
- [X] T037 [P] [US2] Integration test realized FX gain/loss posting on reconciliation, and
  unrealized period-end revaluation + draft next-day reversal, in
  `tests/accounting/test_multi_currency.py`
- [X] T038 [P] [US2] Integration test bank statement continuity rejection and statement-line
  reconciliation (1:1 and 1:N split) in `tests/accounting/test_bank_statement.py`
- [X] T039 [P] [US2] Unit test cash-rounding strategies (`add_invoice_line`, `biggest_tax`) in
  `tests/accounting/test_cash_rounding.py`

### Implementation for User Story 2

- [X] T040 [US2] Extend `AccountMove.action_post` in `dodoo/addons/account/models/account_move.py`:
  for a move whose `currency_id` differs from the company's currency, look up
  `ResCurrencyRate.get_rate(env, currency_id, company_currency_id, move.date)` and derive
  `debit`/`credit` from `amount_currency × rate` for every line (FR-024, ADR-042) (depends on T014)
- [X] T041 [US2] Add `writeoff_account_id`/`writeoff_journal_id` optional parameters to
  `AccountPartialReconcile.reconcile_lines` in
  `dodoo/addons/account/models/account_reconcile.py`: when the residual doesn't net to zero and a
  write-off account is supplied, post a balancing `account.move` via the existing
  `AccountMove.create` + `action_post` path and reconcile it against the remaining residual
  (FR-020, ADR-042)
- [X] T042 [US2] Populate and use `debit_amount_currency`/`credit_amount_currency` in
  `reconcile_lines`: when either line's `currency_id` differs from the company currency, compute
  residuals and full-vs-partial completion in transaction-currency terms (FR-022) (depends on T041)
- [X] T043 [US2] Extend `reconcile_lines` to detect a realized exchange gain/loss (same
  `amount_currency`, different company-currency `amount_residual` from booking at different rates)
  and post it to `res_company.income_currency_exchange_account_id`/
  `expense_currency_exchange_account_id` via the same write-off-style helper move (FR-025, ADR-042)
  (depends on T042, T016)
- [X] T044 [US2] Add `AccountPartialReconcile.suggest_matches(env, payment_id)` classmethod:
  query open `payment_term` lines for the payment's partner ordered by
  `ABS(amount_residual - :amount)` then `similarity(ml.name, :ref)` (`pg_trgm`), return top 10
  (FR-021) (depends on T017)
- [X] T045 [US2] Add `POST /account/reconcile` (direct-callable write-off reconciliation) and
  `GET /account/payment/{id}/suggestions` routes to
  `dodoo/addons/account/http/__init__.py`, with `ReconcileWithWriteOff` /
  (no new payload for suggestions, query params only) validators in
  `dodoo/addons/account/validators.py` (depends on T041, T044)
- [X] T046 [US2] Add `AccountMove.revalue_currency_balances(env, company_id, as_of, uid)`
  classmethod: for every open foreign-currency AR/AP line, post one adjustment move to the exchange
  accounts dated `as_of`, then create its next-day reversal directly in `draft` (a plain
  `AccountMove.create` with reversed debit/credit, no `action_post` call — the general `auto_post`
  parameter on `action_reverse` lands later in US3/T068 and can replace this inline construction
  then) (FR-026, ADR-042); add `POST /account/currency/revalue` route (`RunRevaluation` validator,
  requires `"Accounting Manager"`) (depends on T040)
- [X] T047 [US2] Create `dodoo/addons/account/models/account_bank_statement.py`:
  `AccountBankStatement` (`journal_id`, `date`, `balance_start`, `balance_end_real`, `state`
  [`open`/`confirmed`], `company_id`) and `AccountBankStatementLine` (`statement_id`, `date`,
  `payment_ref`, `partner_id`, `amount`, `move_line_id`) (FR-027, ADR-043)
- [X] T048 [US2] Add `AccountBankStatement.action_confirm` (continuity check against the prior
  statement on the same journal by date) and `get_status` (`balance_start + SUM(lines.amount) ==
  balance_end_real`) to `account_bank_statement.py` (FR-028) (depends on T047)
- [X] T049 [US2] Add `AccountBankStatementLine.reconcile_against(env, line_id, move_line_ids)`:
  1:1 sets `move_line_id`; 1:N splits into child statement lines via bulk-create (FR-029) (depends
  on T047)
- [X] T050 [US2] Add `POST /account/statement/{id}/confirm`, `GET /account/statement/{id}/status`,
  `POST /account/statement/{id}/line/{id}/reconcile` routes plus `BankStatementCreate`,
  `BankStatementLineCreate`, `StatementLineReconcile` validators (depends on T048, T049)
- [X] T051 [US2] Create `dodoo/addons/account/models/account_cash_rounding.py`:
  `AccountCashRounding` (`name`, `rounding`, `rounding_method` [`up`/`down`/`half_up`], `strategy`
  [`add_invoice_line`/`biggest_tax`], `account_id`, `company_id`) (FR-030, ADR-043)
- [X] T052 [US2] Add `invoice_cash_rounding_id` (`Many2one("account.cash.rounding")`, nullable) to
  `AccountMove`; apply it in `action_post` right after tax computation — insert an adjustment line
  (`add_invoice_line`) or adjust the largest tax line (`biggest_tax`) (FR-030) (depends on T051,
  T024); add `CashRoundingCreate` validator
- [X] T053 [P] [US2] ~~Create dedicated `bank-statement-list.js`/`bank-statement-form.js`~~ —
  superseded by registering `account.bank.statement`/`account.bank.statement.line` in
  `dodoo/addons/web/static/app.js`'s generic `_MODEL_LABELS`/`_SECTION_MODEL_PREFIXES` model-view
  registry (the same mechanism `hr`/`fleet`/`stock` models already use), avoiding a redundant
  bespoke view for a plain CRUD screen — minimal-scope choice per the project's existing convention
- [X] T054 [US2] Add "Bank Statements" and "Cash Rounding" entries to
  `dodoo/addons/account/static/account-menu.js`
- [X] T055 [US2] Update `dodoo/addons/account/data/i18n/{en,ar}.json` with new UI strings (write-off,
  suggestions, bank statement, cash rounding) — "Bank Statements"/"Cash Rounding" menu labels were
  already seeded in both catalogs; no further generic-view field labels needed (no dedicated
  write-off/suggestions widget — see T053)
- [X] T056 [US2] Extend `tests/accounting/test_migrations.py`: assert `res_currency_rate`,
  `account_bank_statement`, `account_bank_statement_line`, `account_cash_rounding`, and
  `account_move.invoice_cash_rounding_id` all exist (depends on T014, T47, T51, T52)

**Checkpoint**: reconciliation, multi-currency, bank statements, and cash rounding are all
independently testable and functional.

---

## Phase 5: User Story 3 — Journal entries that cannot be silently altered (Priority: P2)

**Goal**: Chart-of-accounts classification/constraints are enforced; journal numbering is
per-journal and gap-free; posted entries (header and lines) are immutable except via reversal; an
opt-in hash chain makes tampering detectable; fiscal lock dates block back-dated postings unless a
scoped exception is granted.

**Independent Test**: quickstart.md §3 — a direct line edit on a posted entry, two same-type
journals' independent numbering, a reset-then-repost keeping its number, a draft-only reversal, a
hash-chain-verified journal, and a lock-date rejection with an exception grant.

### Tests for User Story 3

- [X] T057 [P] [US3] Unit test `group_id` auto-resolution from code-prefix range, and the
  off-balance/cash-type reconcile constraint (FR-001/002) in `tests/accounting/test_coa_groups.py`
- [X] T058 [P] [US3] Integration test per-journal sequence scoping across two same-type journals,
  concurrent posting in the same journal (fire two `action_post` calls concurrently; assert no
  duplicate/skipped sequence number, exercising `account_sequence`'s existing atomic
  `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`), and `action_cancel`'s draft-only transition
  (FR-003/004) in `tests/accounting/test_journal_sequencing.py`
- [X] T059 [P] [US3] Integration test reused-number-on-repost and `action_reverse(auto_post=False)`
  draft option (FR-005/006) added to `tests/accounting/test_journal_sequencing.py`
- [X] T060 [P] [US3] Integration test hash-chain compute/verify and posted-line write rejection
  (FR-007/008) in `tests/accounting/test_hash_chain_audit_trail.py`
- [X] T061 [P] [US3] Integration test `action_reset_to_draft` rejection for hash-secured and
  lock-dated moves (FR-009) added to `tests/accounting/test_hash_chain_audit_trail.py`
- [X] T062 [P] [US3] Integration test lock-date auto-advance-with-warning (including the exact
  boundary case — a move dated *on* the lock date itself, not just before it, is also blocked) and
  lock-exception grant/revoke/expiry scoping (FR-031/032/033) in
  `tests/accounting/test_lock_dates_exceptions.py`

### Implementation for User Story 3

- [X] T063 [US3] Add `account_account_group` seed rows for the existing default chart of accounts,
  and a `group_id` resolution step in `AccountAccount.create`/`write` in
  `dodoo/addons/account/models/account_account.py` (numeric-string range match against
  `code_prefix_start`/`code_prefix_end`) (FR-001, ADR-037)
- [X] T064 [US3] Add a reconcile constraint to `AccountAccount.create`/`write`: reject
  `reconcile=True` when `account_type == "off_balance"`; force `reconcile=False` for
  `{"off_balance", "asset_cash", "liability_credit_card"}` (FR-002, ADR-037) (depends on T063)
- [X] T065 [US3] Change `AccountMove.action_post` / `AccountPayment.action_post` in
  `dodoo/addons/account/models/account_move.py` / `account_payment.py`: derive the sequence
  `prefix` from the posting journal's own `code` column instead of `_JOURNAL_PREFIX[move_type]`
  (FR-003, ADR-038, research.md D1)
- [X] T066 [US3] Add `AccountMove.action_cancel(env, ids)` classmethod (`draft → cancel` only,
  reusing `STATE_CHOICES`'s existing `"cancel"` value) and `POST /account/move/{id}/cancel` route
  (FR-004, ADR-038, research.md D2)
- [X] T067 [US3] Make `action_post` idempotent on `posted_before=True` moves: reuse the existing
  `name` instead of allocating a new one when no later move in the journal has a lower sequence
  number (FR-005, ADR-038) (depends on T065)
- [X] T068 [US3] Add `auto_post: bool = True` parameter to `action_reverse`; when `False`, skip the
  `action_post` call on the reversal so it stays in `draft`; update `POST /account/move/{id}/reverse`
  to accept the new `auto_post` body field (FR-006, ADR-038)
- [X] T069 [US3] Add `restrict_mode_hash_table` (`Boolean`, default `False`) to `AccountJournal` in
  `dodoo/addons/account/models/account_journal.py`; add `POST /account/journal/{id}/hash-chain`
  route (`HashChainToggle` validator, requires `"Accounting Manager"`) (ADR-039) (depends on T006,
  T007)
- [X] T070 [US3] Add `inalterable_hash` (`Char(64)`, nullable) and `secure_sequence_number`
  (`Integer`, nullable) to `AccountMove`; in `action_post`, when the journal's
  `restrict_mode_hash_table` is `True`, compute
  `sha256(previous_hash + "|" + name + "|" + date + "|" + amount_total + "|" + sorted_line_tuples)`
  and the next `secure_sequence_number` (via `account_sequence` with prefix `f"HASH/{journal.code}"`)
  (FR-007, ADR-039) (depends on T069)
- [X] T071 [US3] Add `AccountMove.verify_hash_chain(env, journal_id)` classmethod (recomputes every
  secured move's hash in order, returns the first mismatch) and
  `GET /account/journal/{id}/verify-hash-chain` route (FR-007) (depends on T070)
- [X] T072 [US3] Add a `write()` override to `AccountMoveLine` in
  `dodoo/addons/account/models/account_move_line.py`: before `super().write()`, read the parent
  move's `state`/`inalterable_hash` and reject the write with the same `DodooError` shape
  `AccountMove.write` uses when the move is `posted` or `cancel` (FR-008) (depends on T070)
- [X] T073 [US3] Add two more rejection conditions to `AccountMove.action_reset_to_draft`:
  `inalterable_hash is not None`, and the move's `date` on/before the applicable effective lock date
  (FR-009) (depends on T070, T076)
- [X] T074 [US3] Create `dodoo/addons/account/models/account_lock_exception.py`:
  `AccountLockException` (`company_id`, `lock_date_field` [Selection of the four lock-date field
  names], `lock_date`, `user_id` [nullable], `journal_id` [nullable], `end_date`, `granted_by_id`,
  `active`) (FR-033, ADR-039) (depends on T016)
- [X] T075 [US3] Add `_get_effective_lock_date(env, company_id, field, user_id, journal_id, today)`
  helper: returns the company's lock date for `field` unless an active, matching, unexpired
  exception exists, in which case `None` (FR-033) (depends on T074)
- [X] T076 [US3] Call `_get_effective_lock_date` from `AccountMove.action_post`/`write` before
  touching a move dated at/before the relevant lock date; on a hit, advance the move's `date` to
  `lock_date + 1 day` and return a non-fatal `warning` in the response payload instead of
  hard-failing (FR-031/032) (depends on T075)
- [X] T077 [US3] Add `POST /account/lock-exception` (`LockExceptionGrant` validator, requires
  `"Accounting Manager"`, sets `granted_by_id` automatically — SEC-003) and
  `DELETE /account/lock-exception/{id}` (soft-revoke via `active=False`) routes (FR-033) (depends
  on T074)
- [X] T078 [P] [US3] ~~Create `lock-exception-list.js`~~ — superseded by registering
  `account.lock.exception` in `dodoo/addons/web/static/app.js`'s generic model-view registry
  (same rationale as T053)
- [X] T079 [US3] Add "Lock Exceptions" entry to `dodoo/addons/account/static/account-menu.js`;
  gate its visibility on `"Accounting Manager"`
- [X] T080 [US3] Update `dodoo/addons/account/data/i18n/{en,ar}.json` with new UI strings (cancel,
  hash chain, lock date, lock exception)
- [X] T081 [US3] Extend `tests/accounting/test_migrations.py`: assert `account_account.group_id`,
  `account_journal.restrict_mode_hash_table`, `account_move.inalterable_hash`/
  `secure_sequence_number`, `account_lock_exception`, and the eight `res_company` columns (T016)
  all exist (depends on T063, T069, T070, T074)

**Checkpoint**: posted entries cannot be silently altered; sequencing is per-journal and gap-free;
lock dates and their exceptions are enforced.

---

## Phase 6: User Story 4 — Reports an accountant can trust and drill into (Priority: P2)

**Goal**: Trial Balance/General Ledger show correct opening balances; every report supports
drill-down; Aged reports separate not-yet-due balances; the Balance Sheet separates current- from
prior-year earnings; a Tax Report aggregates by grid.

**Independent Test**: quickstart.md §4 — a two-period dataset showing opening balances, drill-down
ids on every report row, a mixed-aging Aged Receivables run, a fiscal-year close followed by a
Balance Sheet, and a tagged-tax Tax Report.

### Tests for User Story 4

- [X] T082 [P] [US4] Unit test the opening-balance aggregate query (pre-`date_from` sum) for Trial
  Balance and General Ledger (FR-034) in `tests/accounting/test_reports_opening_balance.py`
  (standalone — `[[accounting-test-isolation]]`)
- [X] T083 [P] [US4] Unit test the 5-bucket aged-report boundary (`current` for `days_overdue <= 0`)
  (FR-036) in `tests/accounting/test_aged_report_buckets.py`
- [X] T084 [US4] Integration test `close_fiscal_year` + fiscal-year-scoped Balance Sheet
  `current_year_earnings` (FR-037) added to `tests/accounting/test_reports_opening_balance.py`
  (standalone)
- [X] T085 [P] [US4] Integration test `account_id`/`move_id` drill-down fields present on all five
  extended report payloads (FR-035) in `tests/accounting/test_reports_opening_balance.py`
  (standalone)
- [X] T086 [P] [US4] Integration test Tax Report aggregation by grid tag across posted invoices/
  bills (FR-016) in `tests/accounting/test_tax_report.py` (standalone —
  `[[accounting-test-isolation]]`)

### Implementation for User Story 4

- [X] T087 [US4] Add a pre-`date_from` opening-balance aggregate query to
  `AccountReportTrialBalance.get_report` and `AccountReportGeneralLedger.get_report` in
  `dodoo/addons/account/models/account_report.py`; merge it into each account's row and, for the
  General Ledger, use it as the running-balance window's starting value (FR-034, ADR-044)
- [X] T088 [US4] Add `account_id` (already selected internally) to all five existing report
  classes' JSON payloads, and a representative `move_id` per line for the P&L/Balance Sheet/Aged
  reports (FR-035) (depends on T087)
- [X] T089 [P] [US4] Add a click-through handler to
  `dodoo/addons/account/static/views/report-view.js`: navigate to
  `#/accounting/journal-entries?account_id=...` (or the specific move for Aged reports), reusing
  the existing journal-entries list view's `account_id` filter (FR-035) (depends on T088)
- [X] T090 [US4] Extend `_BUCKETS` from four to five values (`current`, `b_0_30`, `b_31_60`,
  `b_61_90`, `b_90_plus`) and fix `_bucket_for` to route `days_overdue <= 0` to `current` instead of
  clamping into `b_0_30`, in `account_report.py`'s aged-report logic (FR-036, ADR-044)
- [X] T091 [US4] Change `AccountReportBalanceSheet.get_report`'s current-year-earnings calculation
  from all-time `_pl_rows(env, _PL_TYPES, None, as_of, ...)` to
  `_pl_rows(env, _PL_TYPES, company_fiscal_year_start(as_of), as_of, ...)`, using a new
  `company_fiscal_year_start` helper reading `res_company.fiscalyear_last_month`/
  `fiscalyear_last_day` (FR-037, ADR-044) (depends on T016)
- [X] T092 [US4] Add `AccountMove.close_fiscal_year(env, company_id, fiscal_year_end, uid)`
  classmethod (posts one entry moving the closing year's `_pl_rows` net result into the seeded
  `equity_unaffected` "Retained Earnings" account) and `POST /account/fiscal-year/close` route
  (`FiscalYearClose` validator, requires `"Accounting Manager"`) (FR-037) (depends on T091)
- [X] T093 [US4] Add `AccountReportTax` class to `account_report.py` (aggregates posted
  invoice/bill tax and base amounts grouped by `account.account.tag` via `tag_ids` from US1/T025)
  and `GET /account/report/tax-report` route (FR-016, ADR-040/044) (depends on T025, T088)
- [X] T094 [US4] Add "Tax Report" entry to `dodoo/addons/account/static/account-menu.js`
- [X] T095 [US4] Update `dodoo/addons/account/data/i18n/{en,ar}.json` with new UI strings (opening
  balance, current/not-due bucket, retained earnings, tax report)

**Checkpoint**: all five existing reports plus the new Tax Report show correct, drill-down-capable
figures matching the reference implementation.

---

## Phase 7: User Story 5 — Credit notes, debit notes, and down payments (Priority: P3)

**Goal**: A debit note increases the amount owed on a posted bill/invoice; a down payment is
tracked and netted against its final invoice.

**Independent Test**: quickstart.md §5 — a debit note against a posted vendor bill, and a
down-payment invoice netted against a final invoice.

### Tests for User Story 5

- [X] T096 [P] [US5] Integration test debit-note creation (same `move_type`, verbatim lines,
  `debit_origin_id` set, increases amount owed) (FR-011) in
  `tests/accounting/test_debit_note_downpayment.py`
- [X] T097 [P] [US5] Integration test down-payment netting against a final invoice at posting
  (FR-012) added to `tests/accounting/test_debit_note_downpayment.py`

### Implementation for User Story 5

- [X] T098 [US5] Add `debit_origin_id` (`Many2one("account.move")`, nullable, mirrors
  `reversed_entry_id`) to `AccountMove`; add `action_create_debit_note(env, move_id, uid)`
  classmethod (copies lines verbatim, no sign flip, same `move_type`) and
  `POST /account/move/{id}/debit-note` route (FR-011, ADR-040)
- [X] T099 [US5] Add `"down_payment"` to `AccountMoveLine`'s existing `DISPLAY_TYPE_CHOICES`; add
  `down_payment_origin_id` (`Many2one("account.move")`, nullable) to `AccountMove` (FR-012, ADR-040)
  (depends on T098)
- [X] T100 [US5] Add `AccountMove.apply_down_payments(env, invoice_id)` classmethod, called from
  `action_post` for invoice-type moves: finds posted down-payment moves referencing `invoice_id`
  and inserts one negative `payment_term`-adjacent line reducing the AR balance, reusing
  `_compute_payment_term_lines`'s existing imbalance-driven insertion (FR-012) (depends on T099)
- [X] T101 [P] [US5] Update `dodoo/addons/account/static/views/invoice-form.js`: debit-note action
  button on posted bills/invoices; down-payment line indicator
- [X] T102 [US5] Update `dodoo/addons/account/data/i18n/{en,ar}.json` with new UI strings (debit
  note, down payment)
- [X] T103 [US5] Extend `tests/accounting/test_migrations.py`: assert `account_move.debit_origin_id`
  and `down_payment_origin_id` exist (depends on T098, T099)

**Checkpoint**: debit notes and down payments are usable end to end.

---

## Phase 8: User Story 6 — Analytic accounting roll-up (Priority: P3)

**Goal**: Analytic accounts/plans are real records; a journal item's analytic distribution is
validated against them; an analytic report rolls up posted amounts.

**Independent Test**: quickstart.md §6 — create analytic accounts, distribute a journal item
across them, and confirm the analytic report's roll-up.

### Tests for User Story 6

- [ ] T104 [P] [US6] Unit test `analytic_distribution` validation (unknown analytic-account id, an
  archived/`active=False` analytic-account id, and percentages ≠ 100 ± 0.01 — all three rejected)
  (FR-038) in `tests/analytic/test_analytic_distribution.py`
- [ ] T105 [P] [US6] Integration test `analytic.plan`/`analytic.account` CRUD in
  `tests/analytic/test_analytic_accounts.py`
- [ ] T106 [P] [US6] Integration test `AccountReportAnalytic` roll-up by analytic account/plan
  (FR-039) in `tests/accounting/test_analytic_accounting.py`

### Implementation for User Story 6

- [ ] T107 [US6] Add a validation step to `AccountMoveLine.create`/`write` in
  `account_move_line.py`: when `analytic_distribution` (existing `Json`) is set, every key must
  resolve to an active `analytic.account` id and the values must sum to `100` (±0.01), else
  `DodooError` (FR-038, ADR-045) (depends on T010)
- [ ] T108 [US6] Add `AccountReportAnalytic` class to `account_report.py`: aggregates posted
  `account_move_line.balance × analytic_distribution[key]` grouped by `analytic_account_id` for a
  date range; add `GET /account/report/analytic` route (FR-039) (depends on T107)
- [ ] T109 [P] [US6] Create `dodoo/addons/analytic/static/views/analytic-account-list.js` /
  `analytic-plan-list.js` (reuse existing list/form types)
- [ ] T110 [US6] Add "Analytic Accounts" and "Analytic Report" entries to
  `dodoo/addons/account/static/account-menu.js`
- [ ] T111 [US6] Update `dodoo/addons/account/data/i18n/{en,ar}.json` and create
  `dodoo/addons/analytic/data/i18n/{en,ar}.json` with new UI strings per
  `[[i18n-per-addon-catalogs]]`

**Checkpoint**: analytic accounting is validated and rolls up correctly; all six user stories are
now independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T112 [P] Documentation: verify all nine ADR files from T005 accurately reflect the final
  implementation (Principle V)
- [ ] T113 [P] Create `dodoo/addons/account/data/indexes.py` (account's first — mirrors
  `hr`/`stock`'s `ensure_indexes(env, ddl)` convention): `(account_id, date)` composite for the
  opening-balance queries (PERF-001), `(partner_id, reconciled)` partial index (`WHERE reconciled =
  FALSE`) for reconciliation suggestions (PERF-002), `(currency_id, rate_date DESC)` on
  `res_currency_rate` (PERF-004); wire from `account_data.py`'s seed orchestrator
- [ ] T114 Create `tests/benchmarks/test_accounting_perf.py`: PERF-001 (opening-balance overhead <
  150 ms @ 100k posted lines / 5-year history), PERF-002 (reconciliation suggestion < 300 ms @ 500
  open items), PERF-004 (currency-rate lookup < 50 ms); re-run 001–007's existing report/posting
  benchmarks alongside to confirm no regression (SC-007/PERF-003) (depends on T087, T044, T014,
  T113)
- [ ] T115 [P] Extend `tests/e2e/test_web_ui_a11y.py` for the four new screens (bank statements,
  lock exceptions, analytic accounts, tax report): zero WCAG 2.1 AA violations, keyboard-operable,
  no colour-only status indicator (ACC-001…003)
- [ ] T116 Security hardening pass: confirm OWASP focus areas from plan.md's Constitution Check —
  A01 (only `"Accounting Manager"` can grant a lock exception or toggle hash-chain mode; verified
  by an explicit non-manager-rejection test in `tests/accounting/test_lock_dates_exceptions.py`)
  and A08 (a tampered posted line's hash-chain break is detected by `verify_hash_chain`; verified
  by an explicit tamper test in `tests/accounting/test_hash_chain_audit_trail.py`) (Principle III)
- [ ] T117 Run `quickstart.md` end to end against a fresh install; confirm every numbered scenario
  passes and the Definition of Done checklist is fully satisfied
- [ ] T118 Confirm `tests/accounting/test_reports_opening_balance.py` and
  `tests/accounting/test_tax_report.py` are excluded from any batched/parallel `tests/accounting/`
  run in CI config, per `[[accounting-test-isolation]]`
- [ ] T119 Run the full pre-existing `tests/accounting/` suite (the 6 files predating this
  feature) unchanged and confirm 100% pass, verifying SC-007 (no regression to already-correct
  behavior)
- [ ] T120 Observability review (Principle IX): confirm every new state-changing action added by
  this feature (`action_cancel`, `verify_hash_chain`, hash-chain toggle, lock-exception grant/
  revoke, `revalue_currency_balances`, bank-statement `action_confirm`/`reconcile_against`,
  `action_create_debit_note`, `apply_down_payments`, `close_fiscal_year`) emits a `_log.info(...)`
  structured entry (`extra={"model": ..., "record_id": ..., "event": ...}`) following the exact
  convention already used by `AccountMove.action_post`/`action_reverse`/
  `AccountPartialReconcile.reconcile_lines`; add any missing call sites

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories (creates
  `account`'s first security/validators framework, the `analytic` addon's models, and
  `res.currency.rate`/`account.account.tag`, all consumed by multiple stories below).
- **User Stories (Phase 3–8)**: All depend on Foundational completion.
  - US1 and US2 (P1) have no dependency on each other and can proceed in parallel.
  - US3 (P2) edits the same `AccountMove.action_post`/`write`/`action_reset_to_draft` methods US1
    and US2 also touch — implement US3 after US1/US2 land (or expect merge conflicts if truly
    parallel; the tasks above are written assuming US1 → US2 → US3 sequencing on `account_move.py`).
  - US4 (P2) depends on US1/T025 (`tag_ids`) for its Tax Report and on Foundational/T016's
    fiscal-year columns for its Balance Sheet fix, but its opening-balance/drill-down/aged-bucket
    work is independent of both.
  - US5 (P3) depends only on Foundational (`AccountMove`'s existing fields) — genuinely
    independent of US1–US4.
  - US6 (P3) depends on Foundational's `analytic.account` model (T010) — independent of US1–US5.
- **Polish (Phase 9)**: Depends on all six user stories being complete.

### Within Each User Story

- Tests are written before implementation (and must fail first).
- Model/field changes before the methods that consume them; methods before the HTTP routes that
  expose them; routes before the static views that call them.
- Story complete before moving to the next priority.

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel.
- Within Foundational, T009–T013 (the `analytic` addon) can run in parallel with T014–T017
  (`base`/`account` foundational pieces) — different files.
- US1 and US2 can be staffed in parallel once Foundational is done (different concern areas within
  `account_move.py`, though both ultimately touch `action_post` — coordinate merges).
- US5 and US6 can be staffed in parallel with anything, at any point after Foundational.
- All test tasks marked [P] within a story can run in parallel (different test files or
  independent sections of the same file).

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test discount-net price_subtotal derivation in tests/accounting/test_invoice_discount_tax.py"
Task: "Unit test price-included tax extraction in tests/accounting/test_invoice_discount_tax.py"
Task: "Unit test round_per_line vs round_globally in tests/accounting/test_invoice_discount_tax.py"
Task: "Unit test payment-term validation/due-date fix/early-discount in tests/accounting/test_payment_terms.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md §1 independently
5. Deploy/demo if ready — this alone fixes the highest-frequency accountant-reported bug class
   (wrong invoice/tax/payment-term figures)

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → validate independently → MVP
3. US2 → validate independently (reconciliation/currency/bank/cash now correct)
4. US3 → validate independently (posted entries now tamper-evident and lock-date-safe)
5. US4 → validate independently (reports now correct and drillable)
6. US5, US6 → validate independently (debit notes/down payments, analytic accounting)
7. Polish → benchmarks, accessibility, security review, full regression pass

### Parallel Team Strategy

1. Team completes Setup + Foundational together.
2. Once Foundational is done: Developer A takes US1, Developer B takes US2 in parallel (different
   concern areas, coordinate on shared `account_move.py`/`account_report.py` edits); Developer C
   can start US5 or US6 immediately (fully independent of US1–US4).
3. US3 and US4 follow once US1/US2 land, since both build on top of `action_post`'s
   post-US1/US2 shape.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- This feature is corrective/completive, not a rewrite — every task above either adds a genuinely
  new capability (per the spec's audit) or edits an existing method at the exact point the audit
  found it wrong. No pre-existing, already-correct `account` behavior is touched.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.
- `tests/accounting/`'s 6 pre-existing test files are never modified for correctness — only new
  test files are added, plus incremental extensions to the new `test_migrations.py` (T018).
