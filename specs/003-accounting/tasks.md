# Tasks: Accounting Module

**Input**: Design documents from `specs/003-accounting/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/jsonrpc.md ✅

**Organization**: Tasks grouped by user story; each story independently testable.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Addon Skeleton & Core Field Types)

**Purpose**: Create the addon directory structure and extend the core field system with the three new types required by accounting.

- [ ] T001 Create dodoo/addons/account/ addon skeleton: __manifest__.py (application=True, depends=['base']), __init__.py, models/__init__.py, http/__init__.py, data/__init__.py in dodoo/addons/account/
- [ ] T002 [P] Add Selection field type to dodoo/core/fields.py (VARCHAR(64) column, choices validation list stored on field, `to_sa_column` returns VARCHAR)
- [ ] T003 [P] Add Monetary field type to dodoo/core/fields.py (NUMERIC(20,6) column, Python Decimal, non-negative default 0, nullable=False)
- [ ] T004 [P] Add Json field type to dodoo/core/fields.py (JSONB column, Python dict, nullable)
- [ ] T005 Create docs/adr/ directory and write five ADR files (docs/adr/001-monetary-numeric.md, 002-sequence-counter.md, 003-tax-rounding.md, 004-report-pattern.md, 005-base-model-additions.md); each file follows title/status/context/decision/consequences format from plan.md ADR-001–ADR-005 (Principle V)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Base models (res.currency, res.company, res.partner), account sequence table, and addon registration — must complete before any user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 Create dodoo/addons/base/models/res_currency.py — ResCurrency model (code Char(3) required unique, name Char(64), symbol Char(8), rounding Integer default 2, active Boolean default True); register in dodoo/addons/base/models/__init__.py
- [ ] T007 Create dodoo/addons/base/models/res_company.py — ResCompany model (name Char(128) required, currency_id Many2one('res.currency') required, partner_id Many2one('res.partner') nullable); register in dodoo/addons/base/models/__init__.py
- [ ] T008 Create dodoo/addons/base/models/res_partner.py — ResPartner model (name Char(256) required, company_id Many2one('res.company'), email Char(256), phone Char(64), vat Char(32), active Boolean default True, is_company Boolean default False); register in dodoo/addons/base/models/__init__.py (accounting FK columns added later in T044)
- [ ] T009 Seed default currency (EUR, symbol €, rounding 2) and default company ("My Company", currency EUR) in dodoo/addons/base/data/base_data.py — append to existing seed_base_data(); idempotent (skip if already exists)
- [ ] T010 Create dodoo/addons/account/models/account_sequence.py — helper module with get_next_sequence(conn, prefix, year) → int using INSERT ... ON CONFLICT DO UPDATE ... RETURNING pattern from ADR-002; no ORM model class needed
- [ ] T011 [P] Create dodoo/addons/account/models/account_account.py — AccountAccount model (code Char(64) required, name Char(256) required, account_type Selection(18 values) required, reconcile Boolean default False, currency_id Many2one nullable, active Boolean default True, company_id Many2one('res.company') required); AccountAccountGroup model (name Char(256), code_prefix_start Char(64), code_prefix_end Char(64), parent_id Many2one self nullable, company_id Many2one required)
- [ ] T012 [P] Create dodoo/addons/account/models/account_journal.py — AccountJournal model (name Char(256) required, code Char(10) required, type Selection(sale/purchase/cash/bank/general) required, default_account_id Many2one nullable, suspense_account_id Many2one nullable, currency_id Many2one nullable, company_id Many2one required, active Boolean default True)
- [ ] T013 Register all account models in dodoo/addons/account/models/__init__.py and register account addon in dodoo/addons/__init__.py so the module loader picks it up
- [ ] T014 Add account_sequence DDL table (prefix VARCHAR(32), year INTEGER, last_no INTEGER, PRIMARY KEY(prefix, year)) to dodoo/addons/account/models/account_sequence.py as a raw SQL CREATE TABLE executed during addon install; also add required DB indexes (idx_account_move_state_date, idx_account_move_line_move_id, idx_account_move_line_display_type, idx_account_account_type, idx_account_move_line_account_reconciled) as DDL strings executed at install time via MigrationRunner or direct conn.execute

**Checkpoint**: Base models installed, addon registered — user story phases can begin.

---

## Phase 3: User Story 1 — Customer Invoicing (Priority: P1) 🎯 MVP

**Goal**: Full AR cycle: create draft invoice → auto-generate tax + AR lines → post (balance check, sequence) → register payment → reconcile → mark paid.

**Independent Test**: Create out_invoice for €1,000 + 20% VAT via execute_kw; post it; verify INV/2026/0001 assigned and payment_state=not_paid; register payment of €1,200; verify payment_state=paid and AR line reconciled=true.

### Implementation

- [ ] T015 [US1] Create dodoo/addons/account/models/account_move_line.py — AccountMoveLine model (move_id Many2one required, sequence Integer default 10, account_id Many2one required, partner_id Many2one nullable, name Char(256), date Date required, display_type Selection(product/tax/payment_term/line_section/line_note) default product, debit Monetary default 0, credit Monetary default 0, balance Monetary default 0, amount_currency Monetary nullable, currency_id Many2one nullable, tax_base_amount Monetary default 0, analytic_distribution Json nullable, reconciled Boolean default False, full_reconcile_id Many2one nullable, amount_residual Monetary default 0, tax_line_id Many2one nullable); add Many2many tax_ids junction table account_move_line_tax_rel
- [ ] T016 [US1] Create dodoo/addons/account/models/account_move.py — AccountMove model with all header fields from data-model.md (name Char(64), move_type Selection(7 values) default entry, state Selection(draft/posted/cancel) default draft, payment_state Selection(6 values) default not_paid, journal_id, company_id, currency_id, partner_id, date, invoice_date, invoice_date_due, invoice_payment_term_id, ref Char(256), narration Text, amount_untaxed/tax/total/residual Monetary defaults 0, reversed_entry_id Many2one self nullable, posted_before Boolean default False)
- [ ] T017 [US1] Create dodoo/addons/account/models/account_tax.py — AccountTaxGroup model (name Char(256), sequence Integer default 10, company_id Many2one required); AccountTax model (name Char(256) required, type_tax_use Selection(sale/purchase/none) required, amount_type Selection(percent/fixed/division/group) required, amount Monetary default 0, price_include Boolean default False, include_base_amount Boolean default False, tax_group_id Many2one nullable, company_id Many2one required, active Boolean default True, children_tax_ids Many2many('account.tax', relation_table='account_tax_filiation_rel', column1='parent_id', column2='child_id')); AccountTaxRepartitionLine model (tax_id Many2one required cascade, document_type Selection(invoice/refund) required, repartition_type Selection(base/tax) required, factor_percent Monetary default 100, account_id Many2one nullable, sequence Integer default 10); the account_tax_filiation_rel junction table is auto-created by MigrationRunner from the Many2many field declaration
- [ ] T018 [US1] Implement tax computation engine in dodoo/addons/account/models/account_move.py — method _compute_tax_lines(conn, move_id): fetch product lines + their tax_ids; validate each tax's type_tax_use is compatible with move_type (sale taxes only on out_invoice/out_refund/out_receipt, purchase taxes only on in_invoice/in_refund/in_receipt) — raise ValidationError if mismatch (edge case: purchase tax on customer invoice); for each valid tax compute raw amount (percent: base×rate/100, fixed: amount, division: base×rate/(100−rate), group: delegate to children); accumulate by tax_id; round each total once (round_globally, ADR-003); delete existing tax/payment_term lines; insert new tax lines per repartition line; insert payment_term lines for AR/AP account
- [ ] T019 [US1] Implement action_post in dodoo/addons/account/models/account_move.py: validate state=draft; verify at least one accounting line exists with display_type NOT IN ('line_section','line_note') — raise ValidationError("Cannot post an entry with no accounting lines") if zero lines found (edge case: empty move); call _check_balanced(conn, move_id) — SQL query from plan.md; raise ValidationError if unbalanced with imbalance amount; validate journal/move_type compatibility (FR-007); call get_next_sequence(conn, journal.code, year) to assign move.name; set state=posted, posted_before=True; log OBS-001 structured entry; update amount_untaxed/tax/total from lines; set payment_state=not_paid for invoice-type moves
- [ ] T020 [US1] Implement write/unlink override on AccountMove in dodoo/addons/account/models/account_move.py: reject any write to accounting fields (journal_id, date, line amounts, partner_id) when state=posted; raise ValidationError with SEC-002 message; allow narration/ref edits on posted moves only
- [ ] T021 [US1] Create dodoo/addons/account/models/account_reconcile.py — AccountPartialReconcile model (debit_move_id Many2one required, credit_move_id Many2one required, amount Monetary required, debit_amount_currency Monetary default 0, credit_amount_currency Monetary default 0, full_reconcile_id Many2one nullable, company_id Many2one required); AccountFullReconcile model (company_id Many2one required)
- [ ] T022 [US1] Implement reconcile_lines class method in dodoo/addons/account/models/account_reconcile.py: validate both lines posted, on reconcile=True accounts, same company_id (SEC-004); validate amount ≤ min(debit residual, credit residual); INSERT partial reconcile; UPDATE amount_residual on both lines; check if combined residual = 0 (within currency rounding) → if yes INSERT full_reconcile + UPDATE all participating lines reconciled=True + full_reconcile_id; log OBS-001 structured entry
- [ ] T023 [US1] Implement unreconcile class method in dodoo/addons/account/models/account_reconcile.py: DELETE partial reconcile records; if full_reconcile existed DELETE it; recompute amount_residual on all involved lines; set reconciled=False; log OBS-001 structured entry
- [ ] T024 [US1] Create dodoo/addons/account/models/account_payment.py — AccountPayment model (name Char(64), payment_type Selection(inbound/outbound) required, partner_type Selection(customer/supplier) required, partner_id Many2one required, journal_id Many2one required, currency_id Many2one required, amount Monetary required, date Date required, ref Char(256), state Selection(draft/posted/cancelled) default draft, move_id Many2one nullable, company_id Many2one required)
- [ ] T025 [US1] Implement action_post on AccountPayment: validate journal.type in (cash, bank); validate amount > 0 (SEC-003); create account.move with 2 lines — inbound customer: Dr bank_account Cr AR account; outbound vendor: Dr AP account Cr bank_account; call AccountMove.action_post; assign PAY/YYYY/NNNN name; set state=posted; log OBS-001
- [ ] T026 [US1] Implement register_against_invoices on AccountPayment: validate payment is posted; for each invoice_id fetch AR/AP payment_term lines; call reconcile_lines(payment_ar_line, invoice_ar_line, min(residuals)); collect results; return reconciled_invoice_ids + fully_paid list; update invoice payment_state based on amount_residual
- [ ] T027 [US1] Implement _compute_payment_state in dodoo/addons/account/models/account_move.py: query sum of amount_residual on payment_term lines; if 0 → paid; if full amount → not_paid; if partial → partial; if reversed_entry_id exists and original fully reconciled → reversed
- [ ] T028 [US1] Seed default chart of accounts (22 accounts from plan.md) and 5 journals (INV/BILL/CSH/BNK/MISC) in dodoo/addons/account/data/chart_of_accounts.py — seed_account_data(env) function; idempotent; also seed one default 20% VAT tax (sale) with repartition lines pointing to VAT Collected account
- [ ] T029 [US1] Add HTTP action routes in dodoo/addons/account/http/__init__.py: POST /account/move/<id>/post, POST /account/move/<id>/reset_to_draft, POST /account/payment/<id>/post, POST /account/payment/<id>/register using @route decorator; validate session (SEC-001); delegate to model methods
- [ ] T030 [US1] Register execute_kw custom methods (action_post, action_reset_to_draft, action_reverse, compute_tax_lines, reconcile_lines, unreconcile, register_against_invoices) in the JSON-RPC dispatcher by ensuring they are class methods on the respective models — existing execute_kw already routes any class method by name via getattr

**Checkpoint**: US1 complete — run quickstart Scenario 1 end-to-end.

---

## Phase 4: User Story 2 — Vendor Bills (Priority: P1)

**Goal**: Full AP cycle using in_invoice in purchase journal with outbound payment and AP reconciliation.

**Independent Test**: Create in_invoice for €500 in purchase journal; post → BILL/2026/0001; register outbound payment of €600 (incl. 20% VAT); verify bill payment_state=paid and AP line reconciled.

### Implementation

- [ ] T031 [US2] Enforce journal/move-type compatibility in action_post (dodoo/addons/account/models/account_move.py): sale journal → only out_invoice/out_refund; purchase journal → only in_invoice/in_refund; cash/bank → only via account.payment; general → only entry; raise ValidationError on mismatch
- [ ] T032 [US2] Add purchase tax seed (VAT 20% type_tax_use=purchase) in dodoo/addons/account/data/chart_of_accounts.py pointing to VAT Deductible account (2510); add seed vendor partner "Vendor Corp" in seed data
- [ ] T033 [US2] Verify outbound payment journal entry logic in AccountPayment.action_post (T025) correctly handles partner_type=supplier: Dr AP account / Cr bank account; add integration validation in quickstart Scenario 7

**Checkpoint**: US2 — vendor bill full cycle works independently.

---

## Phase 5: User Story 3 — Credit Notes and Refunds (Priority: P2)

**Goal**: Reversal entries (out_refund/in_refund) that auto-reconcile against the original invoice on posting.

**Independent Test**: Create out_refund via action_reverse on posted INV; post it; verify RINV/2026/0001 assigned; original invoice payment_state=reversed.

### Implementation

- [ ] T034 [US3] Implement action_reset_to_draft in dodoo/addons/account/models/account_move.py: validate state=posted; check no reconciliation exists on any payment_term line (query account_partial_reconcile); if reconciled → raise ValidationError; set state=draft; preserve posted_before=True; log OBS-001
- [ ] T035 [US3] Implement action_reverse in dodoo/addons/account/models/account_move.py: create new account.move with same journal, partner, company; swap debit/credit on all accounting lines (debit↔credit, balance negated); set move_type to counterpart (out_invoice→out_refund, in_invoice→in_refund, entry→entry); set reversed_entry_id=original_move_id; set date from kwargs; post the reversal; auto-reconcile AR/AP lines between original and reversal via reconcile_lines; log OBS-001
- [ ] T036 [US3] Add RINV/YYYY/ and RBILL/YYYY/ sequence prefixes to account_sequence logic in dodoo/addons/account/models/account_sequence.py: when move_type=out_refund use journal.code + 'R' prefix (e.g. RINV); when in_refund use RBILL; add this logic to get_next_sequence caller in action_post

**Checkpoint**: US3 — credit notes reduce original invoice balance correctly.

---

## Phase 6: User Story 4 — Manual Journal Entries (Priority: P2)

**Goal**: Free-form balanced entries in the general journal with MISC/YYYY/NNNN sequence.

**Independent Test**: Create entry move in general journal with Dr Office Supplies €500 / Cr Bank €500; post → MISC/2026/0001; verify it appears in general ledger.

### Implementation

- [ ] T037 [US4] Implement section/note line exclusion: in _check_balanced and all amount computations in dodoo/addons/account/models/account_move.py, add WHERE display_type NOT IN ('line_section', 'line_note') to all SQL queries touching amounts; verify no balance contribution from these lines
- [ ] T038 [US4] Add create validation for tax and payment_term lines in AccountMoveLine: in the create class method, check display_type — if 'tax' or 'payment_term', raise ValidationError("Tax and payment term lines are system-generated and cannot be created directly"); this enforces FR-019

**Checkpoint**: US4 — manual entries post and appear in ledger.

---

## Phase 7: User Story 5 — Chart of Accounts Management (Priority: P2)

**Goal**: CRUD on accounts/groups with type enforcement, soft-delete, balance display, and auto-group assignment.

**Independent Test**: Create account 4000 Revenue; verify in list; compute balance from posted lines; deactivate it; verify it disappears from active list but journal lines on it remain.

### Implementation

- [ ] T039 [US5] Implement reconcile flag enforcement in AccountAccount.write (dodoo/addons/account/models/account_account.py): if account_type in (asset_receivable, liability_payable) and vals.get('reconcile') == False → raise ValidationError (FR-002); also enforce on create: auto-set reconcile=True for these types
- [ ] T040 [P] [US5] Implement off_balance tax restriction: in _compute_tax_lines and in AccountMoveLine.create, check that account.account_type != 'off_balance' before allowing tax_ids; raise ValidationError if violated (FR-025)
- [ ] T041 [P] [US5] Implement account balance computation as class method AccountAccount.get_balance(conn, account_id) → {debit, credit, net}: SQL SELECT ROUND(SUM(debit),2), ROUND(SUM(credit),2), ROUND(SUM(balance),2) FROM account_move_line WHERE account_id=:id AND display_type NOT IN ('line_section','line_note') AND move_id IN (SELECT id FROM account_move WHERE state='posted'); expose via execute_kw callable method
- [ ] T042 [US5] Implement auto-group assignment helper in AccountAccount: class method get_account_group(conn, code, company_id) → group_id | None — query account_account_group WHERE code_prefix_start <= code <= code_prefix_end ORDER BY code_prefix_end - code_prefix_start ASC LIMIT 1; call in AccountAccount.create and write when code changes

**Checkpoint**: US5 — chart of accounts CRUD with all constraints works.

---

## Phase 8: User Story 6 — Tax Configuration (Priority: P2)

**Goal**: Full tax CRUD with all four computation types, price_include, group taxes, and fiscal position mapping.

**Independent Test**: Create percent tax 20% price_include=True; apply to invoice line of €1,200; verify base=€1,000 tax=€200; create group tax with two children; verify both generate separate tax lines.

### Implementation

- [ ] T043 [P] [US6] Create dodoo/addons/account/models/account_fiscal_position.py — AccountFiscalPosition model (name Char(256), company_id Many2one required, active Boolean); AccountFiscalPositionTax mapping (position_id Many2one, tax_src_id Many2one, tax_dest_id Many2one nullable); AccountFiscalPositionAccount mapping (position_id Many2one, account_src_id Many2one, account_dest_id Many2one)
- [ ] T044 [US6] Add accounting FK columns to res.partner via ALTER TABLE in dodoo/addons/account/models/account_account.py module-load hook (or in the account addon's install migration): ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_account_receivable_id INTEGER REFERENCES account_account(id); same for property_account_payable_id, property_payment_term_id, property_supplier_payment_term_id; update ResPartner model class in dodoo/addons/base/models/res_partner.py with these Many2one fields
- [ ] T045 [US6] Implement price_include tax extraction in _compute_tax_lines (dodoo/addons/account/models/account_move.py): when tax.price_include=True, compute base = line_total / (1 + rate/100) for percent taxes; tax amount = line_total - base; adjust product line debit/credit to base amount; generate tax line for remainder
- [ ] T046 [US6] Implement group tax delegation in _compute_tax_lines: when tax.amount_type='group', fetch children_tax_ids via account_tax_filiation_rel junction table; compute each child tax recursively; aggregate under the group for display but post individual repartition lines

**Checkpoint**: US6 — all four tax types compute correctly.

---

## Phase 9: User Story 7 — Payment Terms (Priority: P3)

**Goal**: Multi-installment payment terms that split invoices into multiple AR/AP lines with computed due dates.

**Independent Test**: Create "50/50 Net 30" term; apply to €1,200 invoice; verify 2 payment_term lines: €600 due today, €600 due +30 days.

### Implementation

- [ ] T047 [US7] Create dodoo/addons/account/models/account_payment_term.py — AccountPaymentTerm model (name Char(256) required, note Text, early_discount Boolean default False, discount_percentage Monetary default 0, discount_days Integer default 0, company_id Many2one required, active Boolean); AccountPaymentTermLine model (payment_term_id Many2one required cascade, sequence Integer, value Selection(percent/fixed), value_amount Monetary, delay_type Selection(days_after/days_after_end_of_month/days_after_end_of_next_month/days_end_of_month_on_the), nb_days Integer)
- [ ] T048 [US7] Implement payment term line sum validation in AccountPaymentTerm.write and create (dodoo/addons/account/models/account_payment_term.py): after saving lines, compute sum of percent lines + fixed lines as % of a reference total; if result != 100% raise ValidationError with discrepancy (FR-027); last line treated as residual to absorb rounding
- [ ] T049 [US7] Implement compute_payment_term_lines(conn, move_id, payment_term_id, invoice_date, amount_total) helper in dodoo/addons/account/models/account_move.py: for each payment term line compute due_date (invoice_date + nb_days, or end-of-month variants); compute installment amount (percent × total or fixed); generate payment_term account_move_line rows on AR/AP account with correct partner_id; replace existing payment_term lines

**Checkpoint**: US7 — multi-installment invoices generate correct due-date lines.

---

## Phase 10: User Story 8 — Financial Reports (Priority: P3)

**Goal**: Six read-only financial reports callable via execute_kw returning structured data renderable by existing web UI list view.

**Independent Test**: Post 10 invoices; run Trial Balance; verify totals.balanced=true and response < 5s.

### Implementation

- [ ] T050 [US8] Create dodoo/addons/account/models/account_report.py — six virtual model classes: AccountReportTrialBalance, AccountReportGeneralLedger, AccountReportProfitLoss, AccountReportBalanceSheet, AccountReportAgedReceivable, AccountReportAgedPayable; each class has _name set, no DB table, overrides search_read to return [] and fields_get to return report parameter fields; primary interface is get_report(**kwargs) class method
- [ ] T051 [US8] Implement AccountReportTrialBalance.get_report(conn, date_from, date_to) → {result: [...], totals: {total_debit, total_credit, balanced}}: SQL from plan.md with state='posted' filter and date range; group by account; compute totals; verify balanced flag (abs(total_debit - total_credit) < 0.01)
- [ ] T052 [P] [US8] Implement AccountReportGeneralLedger.get_report(conn, account_id, date_from, date_to) → {result: [...]}: SELECT date, move.name, partner.name, line.name, debit, credit with running_balance as SUM(balance) OVER (ORDER BY date, id) for the given account; state='posted'; chronological order
- [ ] T053 [P] [US8] Implement AccountReportProfitLoss.get_report(conn, date_from, date_to) → {result: {income, expense, net_profit}}: separate queries for internal_group IN ('income') and ('expense'); sum by account; net_profit = sum(income) - sum(expense)
- [ ] T054 [P] [US8] Implement AccountReportBalanceSheet.get_report(conn, date) → {result: {assets, liabilities, equity, totals}}: sum all posted lines up to date for asset/liability/equity accounts; verify assets = liabilities + equity (balanced flag)
- [ ] T055 [P] [US8] Implement AccountReportAgedReceivable.get_report(conn, date) and AccountReportAgedPayable.get_report: for each partner with outstanding amount_residual > 0 on AR/AP payment_term lines, compute days overdue = (date - invoice_date_due); bucket into 0-30, 31-60, 61-90, 90+; return per-partner rows with bucket totals
- [ ] T056 [US8] Add database indexes for PERF-002 via raw DDL executed at addon install in dodoo/addons/account/models/account_sequence.py install hook: CREATE INDEX IF NOT EXISTS idx_account_move_state_date ON account_move(state, date); idx_account_move_line_move_id ON account_move_line(move_id); idx_account_move_line_display_type ON account_move_line(display_type); idx_account_account_type ON account_account(account_type); idx_account_move_line_account_reconciled ON account_move_line(account_id, reconciled)

**Checkpoint**: US8 — all 6 reports return correct data; Trial Balance shows balanced=true.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Critical path tests (Principle II MUST), CI/pre-commit gate, observability, security audit, performance, accessibility, and full quickstart validation.

- [ ] T057 Write pytest integration tests for all critical paths in tests/accounting/ — test_balance_constraint.py (post fails on imbalance, post fails on zero accounting lines, post succeeds on balanced entry); test_reconcile.py (partial reconcile, full reconcile on zero residual, unreconcile, cross-company rejected); test_tax.py (percent 20%, fixed, division, price_include, group delegation, purchase-tax-on-sale-invoice rejected); test_payment_state.py (not_paid → partial → paid transition); these are the 100% critical-path tests per Principle II
- [ ] T058 [P] Write pytest integration tests for state lifecycle in tests/accounting/test_move_lifecycle.py: draft→posted (happy path); reset-to-draft blocked when reconciled; reversal creates mirrored move with reversed_entry_id; empty move rejected; posted move write rejected (SEC-002)
- [ ] T059 [P] Configure pre-commit hooks in .pre-commit-config.yaml: Black (formatting), ruff (linting, zero warnings), and pytest tests/accounting/ (critical path tests must pass before commit); this satisfies Principle VIII's minimum CI gate requirement with no external CI service needed (Principle I enforcement)
- [ ] T060 Audit all state transitions across account_move.py, account_payment.py, account_reconcile.py — verify every action_post, action_reset_to_draft, action_reverse, reconcile_lines, unreconcile emits a structured JSON log entry with move_id/transition/user_id/utc_timestamp using dodoo.core.logging (OBS-001)
- [ ] T061 [P] SEC-001 audit: verify @route decorator on all HTTP endpoints in dodoo/addons/account/http/__init__.py uses auth='session' (not 'public'); confirm unauthenticated request returns HTTP 401
- [ ] T062 [P] SEC-003 audit: add input validation to AccountPayment.action_post (amount > 0), AccountTax amounts (≥ 0), AccountMoveLine amounts (debit ≥ 0, credit ≥ 0, not both > 0); ensure all validations raise ValidationError at the model layer before any DB write
- [ ] T063 [P] SEC-004 audit: verify reconcile_lines checks company_id match between both move lines before any INSERT; covered by T057 test_reconcile.py cross-company test
- [ ] T064 Run quickstart.md validation scenarios 1–8 against a running dodoo instance; verify all 12 pass/fail checkboxes pass; fix any failures before reporting complete
- [ ] T065 [P] SC-006 verification: run tax computation tests from T057 test_tax.py against known manual calculations; verify round_globally produces tax totals matching expected values to within 0.01 of currency unit for percent, division, and group tax types on multi-line invoices (3+ lines)
- [ ] T066 [P] ACC-001: verify monetary amounts in all report outputs are returned with 2 decimal places (round to currency.rounding); ACC-002: verify report dicts use explicit 'debit' and 'credit' keys; verify list view column headers render distinctly
- [ ] T067 PERF-001: time a single account.move read (via execute_kw) on a seeded dataset; confirm < 500 ms; PERF-003: time action_post balance check in isolation; confirm < 100 ms overhead
- [ ] T068 [P] Run Black + ruff across all new/modified files (dodoo/core/fields.py, dodoo/addons/base/models/*.py, dodoo/addons/account/**/*.py); fix all linting errors; zero warnings permitted (Principle I)
- [ ] T069 [P] Dependency audit: run pip-audit against .venv; confirm no HIGH/CRITICAL CVEs introduced; confirm no new packages added beyond existing requirements (Principle VII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phases 3–10 (User Stories)**: Depend on Phase 2; US1 must complete before US2/US3/US4/US5/US6 because the core move/line/tax engine is shared
- **Phase 11 (Polish)**: Depends on all desired user stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — implements the core engine used by all other stories
- **US2 (P1)**: After US1 — reuses move/line/tax engine; adds vendor-specific rules
- **US3 (P2)**: After US1 — uses action_reverse built on US1 engine
- **US4 (P2)**: After US1 — reuses post/balance engine; adds section/note handling
- **US5 (P2)**: After US1 — account CRUD uses move lines for balance computation
- **US6 (P2)**: After US1 — tax config extends tax engine built in US1; fiscal position after US6 base
- **US7 (P3)**: After US1 — payment terms extend payment_term line generation in US1
- **US8 (P3)**: After US1–US6 — reports need all entities posted

### Within Each User Story

- Models before services
- Services (engine methods) before HTTP routes
- Seed data before validation

### Parallel Opportunities (within Phase 2)

- T006, T007, T008, T009 — sequential (company needs currency, partner needs company)
- T011, T012 — can run in parallel (different files)

### Parallel Opportunities (within US1 — Phase 3)

- T015 (move_line) and T017 (tax) can run in parallel
- T021 (reconcile) and T024 (payment) can run in parallel after T015+T016
- T028 (seed data) and T029 (HTTP routes) can run in parallel after T019+T020

---

## Parallel Example: User Story 1

```bash
# Step 1 (parallel): models
Task T015: account_move_line.py
Task T017: account_tax.py

# Step 2 (sequential): core move model
Task T016: account_move.py (depends on T015 table existing)

# Step 3 (parallel): engine methods
Task T018: _compute_tax_lines
Task T021: account_reconcile.py

# Step 4 (sequential): action_post
Task T019: action_post (depends on T018)

# Step 5 (parallel): payment + seed
Task T024: account_payment.py
Task T028: chart_of_accounts seed

# Step 6 (sequential): register payment
Task T025: action_post on payment (depends T024)
Task T026: register_against_invoices (depends T025 + T022)
```

---

## Implementation Strategy

### MVP (US1 + US2 only — Priority P1)

1. Phase 1: Setup (T001–T005)
2. Phase 2: Foundational (T006–T014)
3. Phase 3: US1 Customer Invoicing (T015–T030)
4. **VALIDATE**: Run quickstart Scenarios 1–4 (invoice cycle + imbalance rejection + trial balance + immutability)
5. Phase 4: US2 Vendor Bills (T031–T033)
6. **VALIDATE**: Run quickstart Scenario 7 (vendor bill)

### Incremental Delivery

- After MVP: add US3 (credit notes) → US4 (manual entries) → US5 (CoA mgmt)
- Then: US6 (tax config) → US7 (payment terms) → US8 (reports)
- Each story complete and independently testable before moving to next

---

## Notes

- [P] tasks touch different files and have no blocking dependencies within the phase
- [Story] label maps each task to its user story for traceability
- account_sequence.py is a helper module (no ORM model), not an execute_kw-exposed model
- The virtual report models (account_report.py) override search_read to return [] — only get_report is meaningful
- Seed data functions MUST be idempotent (check exists before insert)
- Every action method must be a classmethod to work with existing execute_kw dispatcher
