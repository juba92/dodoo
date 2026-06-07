# Feature Specification: Accounting Module

**Feature Branch**: `003-accounting`

**Created**: 2026-06-07

**Status**: Draft

## User Scenarios & Testing

### User Story 1 — Customer Invoicing (Priority: P1)

An accountant creates a customer invoice, applies taxes, confirms it, and records payment — completing the full accounts-receivable cycle.

**Why this priority**: Revenue tracking is the most fundamental accounting operation. Without it, no other financial reporting is meaningful. This story alone constitutes a viable MVP that proves the double-entry engine works.

**Independent Test**: Create a customer invoice for €1,000 with 20% VAT, confirm it, register a payment of €1,200, and verify the invoice is marked as fully paid and the general ledger shows balanced debit/credit entries.

**Acceptance Scenarios**:

1. **Given** a confirmed customer, **When** an accountant creates a draft customer invoice with one product line of €1,000 and assigns a 20% VAT tax, **Then** the system auto-generates a tax line of €200 and an accounts-receivable line of €1,200, and the entry is perfectly balanced (total debits = total credits = €1,200).
2. **Given** a draft invoice, **When** the accountant confirms (posts) it, **Then** the system assigns a unique sequential reference (e.g. INV/2026/0001), locks the invoice against editing, and sets its payment status to "Not Paid".
3. **Given** a posted invoice, **When** the accountant registers a payment of €1,200 against it, **Then** the system creates a payment journal entry (Dr Bank / Cr Accounts Receivable), reconciles the AR lines, and changes the invoice payment status to "Paid".
4. **Given** a posted invoice with payment status "Not Paid", **When** the accountant registers a partial payment of €600, **Then** the payment status becomes "Partial" and the outstanding balance shows €600.
5. **Given** a posted invoice, **When** the accountant attempts to edit a field directly, **Then** the system rejects the edit with a clear message stating the invoice must be reset to draft first.
6. **Given** a posted and unreconciled invoice, **When** the accountant resets it to draft, **Then** the invoice becomes editable and the original sequence number is preserved but not reused for new invoices.

---

### User Story 2 — Vendor Bills (Priority: P1)

An accountant records a vendor bill, confirms it, and registers payment — completing the full accounts-payable cycle.

**Why this priority**: Expense tracking is equally fundamental. Together with US1, these two stories represent complete double-entry bookkeeping for both sides of the business.

**Independent Test**: Create a vendor bill for €500 with 20% VAT, confirm it, register an outbound payment, and verify the bill is marked paid with the AP account fully reconciled.

**Acceptance Scenarios**:

1. **Given** a vendor partner, **When** an accountant creates a draft vendor bill with a purchase line and purchase tax, **Then** the system auto-generates a tax line and an accounts-payable line, and the entry is balanced.
2. **Given** a draft vendor bill, **When** the accountant confirms it, **Then** the system assigns a BILL/YYYY/NNNN reference and sets payment status to "Not Paid".
3. **Given** a posted vendor bill, **When** the accountant registers an outbound payment, **Then** the system creates a payment entry (Dr Accounts Payable / Cr Bank), reconciles the AP lines, and marks the bill as "Paid".
4. **Given** a vendor bill, **When** a vendor provides a reference number, **Then** the accountant can record it in the vendor reference field for cross-referencing.

---

### User Story 3 — Credit Notes and Refunds (Priority: P2)

An accountant issues a credit note against an existing invoice (customer or vendor) to reverse or reduce an outstanding obligation.

**Why this priority**: Corrections are a routine accounting need. Without credit notes, errors in posted invoices cannot be corrected in an audit-safe way.

**Independent Test**: Create a customer credit note that references an existing posted invoice, confirm it, and verify the original invoice's outstanding balance is reduced by the credit amount.

**Acceptance Scenarios**:

1. **Given** a posted customer invoice, **When** the accountant creates a customer credit note and links it to the original invoice, **Then** the credit note is of type "out_refund", uses a RINV/YYYY/NNNN reference, and upon posting auto-reconciles against the original invoice's AR line.
2. **Given** a full credit note equal to the invoice amount, **When** it is posted, **Then** the original invoice's payment status changes to "Reversed" and both entries show as fully reconciled.
3. **Given** a partial credit note for half the invoice amount, **When** it is posted, **Then** the original invoice's outstanding balance is reduced by that amount and status becomes "Partial".
4. **Given** a posted vendor bill, **When** a vendor credit is received, **Then** the accountant can create an "in_refund" credit note to reduce the AP balance.

---

### User Story 4 — Manual Journal Entries (Priority: P2)

An accountant creates free-form journal entries for adjustments, accruals, and corrections that don't fit the invoice workflow.

**Why this priority**: Manual entries are essential for period-end adjustments, depreciation, and any transaction that isn't a commercial invoice or payment.

**Independent Test**: Create a manual journal entry in the general journal with two lines (one debit, one credit) totaling the same amount, confirm it, and verify it appears in the general ledger.

**Acceptance Scenarios**:

1. **Given** the general journal, **When** an accountant creates a manual entry with a debit line of €500 to Office Supplies and a credit line of €500 to Bank, **Then** the system accepts it and assigns a MISC/YYYY/NNNN reference on posting.
2. **Given** a manual entry where debit total ≠ credit total, **When** the accountant attempts to post, **Then** the system rejects it with a message showing the imbalance amount.
3. **Given** a draft manual entry, **When** the accountant adds a section header line, **Then** it appears in the entry for organisational purposes but is excluded from all amount computations.
4. **Given** a posted manual entry, **When** the accountant needs to correct it, **Then** they can create a reversal entry (mirror with debits/credits swapped) rather than editing the original.

---

### User Story 5 — Chart of Accounts Management (Priority: P2)

An accountant manages the company's chart of accounts: creating, viewing, and organising general ledger accounts.

**Why this priority**: The chart of accounts is the backbone of all accounting. It must exist and be manageable before any entries can be recorded.

**Independent Test**: Create a new revenue account with code 4000, verify it appears in the chart of accounts list, and confirm it cannot be deleted once it has journal entries posted to it.

**Acceptance Scenarios**:

1. **Given** no account with code 4000, **When** an accountant creates an income account with code 4000 and name "Product Revenue", **Then** it appears in the chart of accounts and is available for selection on invoice lines.
2. **Given** an asset_receivable account, **When** an accountant attempts to disable the reconcile flag, **Then** the system rejects the change because asset_receivable accounts must always be reconcilable.
3. **Given** an account, **When** an accountant deactivates it (soft-delete), **Then** existing journal entries on that account are preserved and visible in reports, but the account no longer appears for selection on new entries.
4. **Given** account groups with code prefix ranges, **When** an accountant creates account code 4100, **Then** it is automatically assigned to the account group whose prefix range includes 4100.
5. **Given** a chart of accounts, **When** an accountant views an account, **Then** they can see the current debit balance, credit balance, and net balance computed from all posted journal entry lines.

---

### User Story 6 — Tax Configuration (Priority: P2)

An accountant configures tax rates and rules that are automatically applied when creating invoices and bills.

**Why this priority**: Tax automation eliminates manual calculation errors and ensures consistent application of tax rules across all documents.

**Independent Test**: Define a 20% VAT sales tax with the correct accounts, assign it to an invoice product line, and verify the system automatically computes and posts the correct tax amount.

**Acceptance Scenarios**:

1. **Given** no 20% VAT tax, **When** an accountant creates a percentage tax named "VAT 20%" with amount 20, type "sale", and a tax account for the collected VAT, **Then** it is available for selection on customer invoice lines.
2. **Given** a product line with €1,000 and "VAT 20%" applied, **When** the accountant saves the invoice, **Then** the system automatically adds a tax line of €200 posting to the VAT Collected account.
3. **Given** a tax marked "price included", **When** an accountant enters a line total of €1,200, **Then** the system computes the base as €1,000 and the tax as €200.
4. **Given** a fixed-amount tax of €5, **When** it is applied to any invoice line regardless of amount, **Then** the tax line is always €5.
5. **Given** a group tax containing two component taxes, **When** the group is applied, **Then** both component taxes are computed and separate tax lines are generated for each.

---

### User Story 7 — Payment Terms (Priority: P3)

An accountant configures payment terms (e.g. Net 30, 50% now + 50% in 30 days) and assigns them to customers and vendors.

**Why this priority**: Payment terms are needed for accurate due-date tracking and cash flow management, but the system functions without them (single due date as default).

**Independent Test**: Define a "50/50 Net 30" term, apply it to a €1,000 invoice, and verify the invoice generates two payment-term lines: €500 due immediately and €500 due in 30 days.

**Acceptance Scenarios**:

1. **Given** a payment term "Net 30 days", **When** it is assigned to a €1,200 invoice dated 1 June, **Then** the invoice's due date is set to 1 July and a single AR payment-term line of €1,200 is created.
2. **Given** a payment term with two lines (50% immediately, 50% in 30 days), **When** it is applied to a €1,200 invoice, **Then** two payment-term lines are created: €600 due today and €600 due in 30 days.
3. **Given** a partner with a default payment term, **When** an invoice is created for that partner, **Then** the payment term is pre-populated automatically.
4. **Given** a payment term with an early payment discount of 2% if paid in 10 days, **When** it is configured, **Then** the discount percentage and days are stored and visible on invoices using this term.

---

### User Story 8 — Financial Reports (Priority: P3)

An accountant runs standard financial reports to review the company's financial position and performance.

**Why this priority**: Reports are the output of the accounting system — they prove correctness. However, they depend on all prior stories being implemented and working correctly.

**Independent Test**: After posting a set of invoices and payments, run the Trial Balance report and verify that total debits equal total credits.

**Acceptance Scenarios**:

1. **Given** posted journal entries, **When** an accountant requests a Trial Balance, **Then** the system lists each account with its total debit, total credit, and net balance, and the grand totals of all debits equal all credits.
2. **Given** a fiscal period, **When** an accountant requests a Profit & Loss report, **Then** the system shows all income and expense account balances for the period, with net profit computed as income minus expenses.
3. **Given** a Balance Sheet request, **When** the accountant specifies an as-of date, **Then** the system shows all asset, liability, and equity account balances as of that date, with assets equalling liabilities plus equity.
4. **Given** posted customer invoices with outstanding balances, **When** an accountant requests an Aged Receivables report, **Then** the system buckets outstanding AR amounts into 0–30, 31–60, 61–90, and 90+ days overdue based on due dates.
5. **Given** the General Ledger report for a specific account, **When** an accountant selects a date range, **Then** the system lists every posted journal line on that account in chronological order with a running balance.

---

### Edge Cases

- **Posting an empty move**: A journal entry with zero lines must be rejected on posting with a clear error.
- **Negative invoice amounts**: A product line with a negative quantity or price must still produce a balanced entry with correct sign reversals.
- **Same-currency reconciliation rounding**: When reconciling two lines where floating-point arithmetic produces a residual of less than 0.01 in the company currency, the reconciliation should still complete fully.
- **Deactivating an account with open balances**: Accounts with a non-zero balance should warn the user before deactivation but must not prevent it (soft-delete is allowed).
- **Duplicate sequence numbers**: The system must guarantee that no two posted moves in the same journal share the same reference number, even under concurrent conditions.
- **Resetting a partially-reconciled invoice to draft**: Must be blocked — once any reconciliation exists on the invoice's lines, reset-to-draft is forbidden until the reconciliation is manually undone.
- **Applying a purchase tax on a customer invoice**: The system must warn or prevent using a `type_tax_use=purchase` tax on a sale-type invoice.
- **Payment term lines not summing to 100%**: Must be rejected on save with a clear error showing the discrepancy.

## Requirements

### Functional Requirements

**Chart of Accounts**
- **FR-001**: The system MUST support a chart of accounts with 18 distinct account types covering all balance-sheet and P&L categories.
- **FR-002**: The system MUST enforce that accounts of type `asset_receivable` and `liability_payable` always have the reconcilable flag enabled; attempts to disable it must be rejected.
- **FR-003**: The system MUST support account groups with code prefix ranges and auto-assign accounts to groups based on their code.
- **FR-004**: The system MUST support soft-deletion of accounts (deactivation) while preserving all historical journal entries on deactivated accounts.
- **FR-005**: The system MUST compute and expose the current debit balance, credit balance, and net balance for each account from all posted journal lines.

**Journals**
- **FR-006**: The system MUST support five journal types: sale, purchase, cash, bank, and general.
- **FR-007**: The system MUST enforce journal/move-type compatibility: customer invoices and credit notes only in sale journals; vendor bills and refunds only in purchase journals; payments only in bank or cash journals.
- **FR-008**: Each journal MUST maintain its own independent numbering sequence, resetting or continuing per fiscal year in the format `PREFIX/YYYY/NNNN`.

**Journal Entries (Moves)**
- **FR-009**: The system MUST support seven move types: manual entry, customer invoice, customer credit note, vendor bill, vendor credit note, customer receipt, and vendor receipt.
- **FR-010**: The system MUST enforce the double-entry balance constraint: posting must fail with a descriptive error if the sum of debits does not equal the sum of credits on all accounting lines.
- **FR-011**: The system MUST implement a three-state lifecycle: draft (editable) → posted (locked, immutable) → cancelled (via reversal only).
- **FR-012**: The system MUST assign the sequential reference number only at posting time, not at creation.
- **FR-013**: Once a move has been posted at least once (`posted_before = true`), resetting to draft must not recycle the sequence number — the gap is preserved for audit integrity.
- **FR-014**: Cancellation of posted entries MUST be implemented as a reversal: a new mirror entry with all debits and credits swapped, linked to the original via a back-reference.
- **FR-015**: The system MUST compute the payment status of invoice-type moves (not_paid, partial, in_payment, paid, reversed, blocked) based on the reconciliation state of the AR/AP lines.

**Journal Entry Lines**
- **FR-016**: The system MUST support five line types: product lines (amounts), tax lines (auto-generated), payment-term lines (auto-generated AR/AP due-date splits), section headers (no amounts), and notes (no amounts).
- **FR-017**: The system MUST enforce that debit and credit values on a line are both non-negative and never simultaneously greater than zero.
- **FR-018**: The system MUST require a partner on every line posted to a receivable or payable account.
- **FR-019**: Tax lines and payment-term lines MUST be auto-generated by the system when a product line is saved or when the invoice is confirmed; they must not be directly created or deleted by the user through the standard interface.
- **FR-020**: Section and note lines MUST be excluded from all accounting computations (balance, tax totals, reconciliation).

**Taxes**
- **FR-021**: The system MUST support four tax computation methods: percentage of base, fixed amount, division (tax-inclusive extraction), and group (delegates to child taxes).
- **FR-022**: The system MUST support tax repartition lines defining where tax amounts are posted for invoices and separately for credit notes, with configurable factor percentages to support reverse-charge scenarios.
- **FR-023**: The system MUST auto-generate tax lines on invoice moves based on the taxes assigned to each product line when the invoice is saved or confirmed. Tax amounts MUST be rounded globally (sum all tax amounts across lines first, then round the total once to the currency's smallest unit) to prevent per-line rounding gaps from violating the balance constraint.
- **FR-024**: The system MUST support fiscal positions that automatically substitute taxes and accounts based on the partner's location.
- **FR-025**: The system MUST prevent taxes from being assigned to accounts of type `off_balance`.

**Payment Terms**
- **FR-026**: The system MUST support payment terms with multiple installment lines, each defining a percentage or fixed amount and a due-date calculation rule.
- **FR-027**: The system MUST validate that payment term lines sum to exactly 100% of the invoice total; reject saving if they do not.
- **FR-028**: When a payment term is applied to an invoice, the system MUST generate one payment-term line per installment on the journal entry, each with its own due date.

**Payments**
- **FR-029**: The system MUST support recording payments (both inbound and outbound) that create a balanced journal entry in a bank or cash journal.
- **FR-030**: Posting a customer payment MUST debit the bank/cash account and credit the customer's AR account; posting a vendor payment MUST debit the vendor's AP account and credit the bank/cash account.
- **FR-031**: The system MUST support registering a payment against one or more outstanding invoices and auto-reconciling the matched AR/AP lines.

**Reconciliation**
- **FR-032**: The system MUST support partial reconciliation between any debit line and any credit line on accounts with the reconcilable flag, recording the matched amount without requiring full settlement.
- **FR-033**: The system MUST create a full-reconciliation record and mark all involved lines as fully reconciled when their combined residual reaches zero.
- **FR-034**: The system MUST support unreconciling (undoing a match), which deletes the partial and full reconcile records and restores the original residual amounts.
- **FR-035**: Only lines belonging to posted journal entries may participate in reconciliation; draft and cancelled lines must be excluded.

**Financial Reports**
- **FR-036**: The system MUST provide a Trial Balance report showing each account's total posted debits, total posted credits, and net balance for a given date range, with grand totals proving the ledger is balanced.
- **FR-037**: The system MUST provide a General Ledger report listing every posted journal line for a specified account in chronological order with a running balance.
- **FR-038**: The system MUST provide a Profit & Loss report showing income and expense account balances for a specified period, with a net profit/loss figure.
- **FR-039**: The system MUST provide a Balance Sheet report showing asset, liability, and equity account balances as of a specified date.
- **FR-040**: The system MUST provide Aged Receivables and Aged Payables reports bucketing outstanding AR/AP amounts into 0–30, 31–60, 61–90, and 90+ days overdue from the invoice due date.

**Integration**
- **FR-041**: The system MUST extend the partner record with default receivable account, default payable account, default customer payment term, and default supplier payment term.
- **FR-042**: All accounting models MUST be accessible via the existing JSON-RPC execute_kw interface (fields_get, search_read, read, create, write, unlink) so the existing web UI can render them without modification.
- **FR-043**: The system MUST provide six document sequences: INV/YYYY/ (customer invoices), BILL/YYYY/ (vendor bills), RINV/YYYY/ (customer credit notes), RBILL/YYYY/ (vendor credit notes), PAY/YYYY/ (payments), MISC/YYYY/ (manual entries).

### Key Entities

- **account.account**: A general-ledger account identified by a code and type; holds no data itself but collects journal lines posted to it.
- **account.account.group**: A named range of account codes used to aggregate accounts into reporting subtotals.
- **account.journal**: A named ledger book that classifies and sequences journal entries of a given type (sale, purchase, bank, cash, general).
- **account.move**: A balanced set of debit/credit journal lines representing a single financial transaction (invoice, bill, payment, or adjustment).
- **account.move.line**: A single debit or credit posting within a journal entry, referencing one GL account and optionally one partner.
- **account.tax**: A rule for computing an additional amount on a transaction base, with configuration for how and where the amount is posted.
- **account.tax.group**: A label grouping related taxes for display as subtotals on invoice documents.
- **account.tax.repartition.line**: Specifies the portion of a tax amount that posts to a given account, for both invoice and credit-note scenarios.
- **account.fiscal.position**: A mapping rule that substitutes taxes and accounts automatically when a partner belongs to a specific country or region.
- **account.payment.term**: A named schedule defining how an invoice total is split into one or more installments with computed due dates.
- **account.payment.term.line**: One installment definition within a payment term.
- **account.payment**: A recorded payment event (inbound or outbound) that generates a journal entry and can be reconciled against one or more invoices.
- **account.partial.reconcile**: A record of a partial match between one debit and one credit journal line on a reconcilable account.
- **account.full.reconcile**: A record created when a group of partial reconciles brings the combined residual to zero, marking all involved lines as fully settled.

### Security Requirements

- **SEC-001**: All accounting API endpoints MUST require an authenticated session; unauthenticated requests must be rejected with HTTP 401.
- **SEC-002**: Posted journal entries MUST be immutable through the API; any write attempt on a posted move's accounting fields must be rejected with HTTP 400.
- **SEC-003**: All monetary inputs (amounts, tax rates, quantities) MUST be validated as non-negative numbers within reasonable bounds at the API boundary.
- **SEC-004**: Reconciliation operations MUST verify that both lines belong to the same company before matching to prevent cross-company data leakage.

### Observability Requirements

- **OBS-001**: Every accounting state transition (draft→posted, posted→draft reset, reconciliation created, reconciliation undone) MUST emit a structured JSON log entry at INFO level containing: move ID, transition name, user ID, and UTC timestamp. No additional database table is required; server-level log infrastructure is used.

### Performance Requirements

- **PERF-001**: Any single accounting model record (invoice, journal entry, payment) must be retrievable in under 500 ms under normal single-user load.
- **PERF-002**: Financial reports (Trial Balance, P&L, Balance Sheet) must compute in under 5 seconds for a ledger containing up to 50,000 posted journal lines.
- **PERF-003**: The balance constraint check on posting must not add more than 100 ms overhead compared to an unvalidated write.

### Accessibility Requirements

- **ACC-001**: All monetary amounts in reports and forms MUST be displayed with consistent currency symbol, thousand separators, and decimal places appropriate to the currency.
- **ACC-002**: Debit and credit columns in reports MUST be visually distinguishable by more than colour alone (label or position).

## Success Criteria

### Measurable Outcomes

- **SC-001**: An accountant can complete the full customer-invoice-to-paid cycle (create, tax, confirm, pay, reconcile) in under 3 minutes without errors.
- **SC-002**: The system rejects 100% of unbalanced journal entries at posting time with a message that identifies the imbalance amount.
- **SC-003**: The Trial Balance report grand totals show zero net imbalance (total debits = total credits) across all posted entries at all times.
- **SC-004**: All five financial reports (Trial Balance, General Ledger, P&L, Balance Sheet, Aged Receivables/Payables) return correct results within 5 seconds for a dataset of 10,000 posted moves.
- **SC-005**: No posted journal entry can be directly modified or deleted through any API path; 100% of such attempts return an error.
- **SC-006**: Tax amounts on invoices match manual calculations to within the currency's smallest unit (e.g. €0.01 for EUR) for all four tax computation methods.
- **SC-007**: The accounting module installs cleanly on a fresh dodoo instance and all accounting models are immediately browsable via the existing web UI without UI code changes.

## Assumptions

- The company operates with a single functional currency. The data model includes `amount_currency` and `currency_id` fields on move lines (nullable, defaulting to the company currency) so the schema is forward-compatible with a future multi-currency module; however, no exchange-rate computation, revaluation, or currency-difference journal entries are produced in this module. All business logic enforces that line amounts in company currency are always authoritative.
- A default chart of accounts is seeded at installation containing approximately 25 accounts with conventional codes and names (e.g. 1100 Accounts Receivable, 1010 Bank, 2000 Accounts Payable, 2010 VAT Payable, 3000 Equity, 4000 Revenue, 5000 Expenses). The set covers every account type category with realistic names sufficient to run all user stories end-to-end. A full country-specific localisation chart is deferred to a future `account_l10n_*` addon following Odoo's pattern.
- The `res.currency` table in the base module already contains currency data and is used directly; no new currency management is built in this module.
- Products and product lines are out of scope; invoice product lines are free-text descriptions with a manually entered unit price and quantity (no product catalogue required at this stage).
- A single company context is assumed throughout; the `company_id` field is stored but multi-company isolation enforcement is deferred.
- The existing web UI's generic list and form views are sufficient to interact with all accounting models; no custom accounting-specific UI screens are required in this module.
- Fiscal year configuration is assumed to follow the calendar year (1 Jan – 31 Dec) by default; custom fiscal year periods are out of scope.
- Bank statement import from external files (OFX, CSV, MT940) is out of scope.
- PDF invoice generation and email sending are out of scope.

## Clarifications

### Session 2026-06-07

- Q: Should `amount_currency` and `currency_id` be stored on move lines now (forward-compatible) or omitted until a multi-currency module is built? → A: Store as nullable fields (forward-compatible schema); enforce single-currency at business logic layer — no exchange-rate logic in this module.
- Q: What is the scope of the default chart of accounts seeded at installation? → A: Minimal functional set (~25 accounts) with conventional codes and real names covering all 18 account types; full localisation charts deferred to future l10n addons.
- Q: How should tax amounts be rounded on multi-line invoices? → A: Round globally — sum all tax amounts first, then round the total once (matching Odoo's `round_globally` default); eliminates per-line rounding gaps that would violate the balance constraint.
- Q: Is per-transition audit logging in scope? → A: Structured server-log entries only (JSON, INFO level, every state transition); no dedicated DB audit table — satisfies constitution observability requirement without extra scope.
