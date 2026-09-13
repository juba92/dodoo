# Feature Specification: Accounting Parity with Odoo 19 Community

**Feature Branch**: `008-accounting-parity`

**Created**: 2026-09-13

**Status**: Draft

**Input**: User description: "Bring dodoo's Accounting module to full functional and behavioral parity with Odoo 19.0 Community's Accounting app, so that a professional accountant can perform their day-to-day bookkeeping in dodoo without hitting a missing capability or a result that doesn't match standard double-entry accounting practice. An accountant evaluated the current implementation and found both missing functionality and incorrect calculations, compared against `../odoo-19.0/addons/account` as the reference implementation. Every gap and divergence must be recorded as a distinct, testable requirement; already-correct behavior must be left alone. Fixed-asset depreciation and budgeting are explicitly out of scope (absent from Community)."

## Audit Summary

A file-by-file comparison of `dodoo/addons/account` (plus `dodoo/addons/stock_account` and `dodoo/addons/product` at their integration points) against `../odoo-19.0/addons/account` found the following classes of divergence. Each is expanded into testable requirements below.

- **Chart of accounts**: accounts are never linked to their account group, and off-balance/cash-type accounts can be marked reconcilable when they shouldn't be.
- **Journals & entries**: sequence numbers are shared across journals of the same move type instead of scoped per journal; there is no "Cancelled" state distinct from "Draft"; re-posting a draft-reset entry burns a new number instead of reusing the original; reversal always force-posts with no draft-review option; posted entries have no tamper-evident hash chain; posted **journal entry lines** can be freely edited even though the entry header is protected; resetting a posted entry to draft only checks reconciliation, never lock dates or hash state.
- **Invoicing**: no per-line discount field exists at all; no debit-note capability; no down-payment capability.
- **Taxes**: computed on the undiscounted base; no tax-inclusive (price-included) pricing; rounding method is hardcoded to "round globally" with no per-company configuration; no tax grids and no tax report.
- **Payment terms**: no validation that installment percentages sum to 100%; early-payment-discount fields exist on the model but are never read anywhere — they have zero functional effect; the "end of month on the Nth day" due-date rule is computed incorrectly.
- **Payments & reconciliation**: only exact-amount matching is possible — no write-off postings, no auto-suggested matches by partner/amount/reference; `amount_currency` fields exist on reconciliation records but are never populated or used.
- **Multi-currency**: there is no dated exchange-rate table at all; `amount_currency` is stored but never converted into company-currency debit/credit, making `currency_id` decorative; no realized exchange gain/loss is ever posted on reconciliation; no period-end unrealized-gain/loss revaluation exists.
- **Bank & cash**: there is no bank statement entity or bank-statement-line reconciliation at all — payments post directly with nothing to check them against; no cash-rounding profile exists.
- **Fiscal periods**: there are no lock dates of any kind (fiscal-year, tax, sales, purchases) and therefore no protection against back-dated edits, no date-forward rollover past a violated lock, and no scoped lock-exception mechanism.
- **Financial reports**: no tax report exists; Trial Balance and General Ledger both drop prior-period activity instead of showing an opening balance when a date filter is applied; no report supports drill-down into source entries; Aged Receivable/Payable has no separate "not yet due" bucket; the Balance Sheet conflates current-year earnings with prior-year retained earnings because there is no fiscal-year-closing mechanism.
- **Analytic accounting**: this is a genuine Odoo 19 Community feature (not Enterprise-only), and dodoo has only an inert, unbacked JSON field for it — no analytic accounts, plans, or roll-up reporting exist.

## Clarifications

### Session 2026-09-13

- Q: Should the new dated exchange-rate table (FR-023) be populated only by manual entry, or must dodoo also integrate with an external rate-provider service (e.g., a central-bank feed) to auto-fetch rates, as Odoo Community optionally supports? → A: Manual entry only for this feature; automatic external-provider fetching is out of scope. Rationale: the accountant's complaint was that currency conversion produces wrong/missing results, not that rate entry is inconvenient — a dated rate table with manual entry fully resolves the correctness gap (FR-023–FR-026) without adding a new external network dependency and its attendant security/reliability surface (Principle III). Automatic fetching can be layered on later without changing the data model.
- Q: Should bank statement entry (FR-027) require parsing specific external file formats (CSV/OFX/CAMT.053), or is manual/API-driven creation of statement lines sufficient? → A: Manual/API-driven entry only; specific file-format import is out of scope. Rationale: the audited gap is the complete absence of a bank-statement concept to reconcile against, not the absence of a particular import format — a statement entity with structured line creation (FR-027–FR-029) resolves the correctness/completeness gap. File-format parsers are additive integrations that don't change how balances, continuity checks, or reconciliation behave, so they are deferred to keep this feature's scope to what the audit actually found broken or missing.

### User Story 1 - Correct invoice, tax, and payment-term figures (Priority: P1)

An accountant creates a customer invoice or vendor bill with a per-line discount, a tax that may be price-included or price-excluded, and a multi-installment payment term with an early-payment discount. The invoice's subtotal, tax amount, total, and due-date schedule must match what Odoo 19 Community would compute for the same inputs.

**Why this priority**: Every single invoice or bill touches line computation, tax computation, and payment terms — this is the highest-frequency workflow in day-to-day bookkeeping, and it is where the accountant found the most numerically wrong results.

**Independent Test**: Create an invoice with a 10% line discount and a 15% tax on the same line, using a payment term with a 2%/10-days early-payment discount; verify the tax base, tax amount, total, due date, and discounted-payment amount each match the reference calculation, independent of any reporting or reconciliation work.

**Acceptance Scenarios**:

1. **Given** an invoice line with quantity, unit price, and a 10% discount, **When** the line is saved, **Then** the tax is computed on the discounted price, not the gross price.
2. **Given** a tax configured as "price included," **When** it is applied to a line, **Then** the tax amount is extracted from the gross price rather than added on top of it.
3. **Given** a payment term with three installment lines of 40%/30%/30%, **When** the term is saved, **Then** the system accepts it because the percentages sum to 100%, and rejects a term whose lines do not sum to 100%.
4. **Given** a payment term with an early-payment discount of 2% within 10 days, **When** an invoice using that term is evaluated for payment within the discount window, **Then** the discounted amount due and its discount due-date are computed and exposed to the payment flow.
5. **Given** a payment term with an "end of month, due on the Nth day" rule, **When** the due date is computed, **Then** it lands on the configured day of the target month, not on the literal end of the current month.

---

### User Story 2 - Reliable reconciliation, multi-currency, and cash handling (Priority: P1)

An accountant registers a payment against one or more open invoices, including cases where the payment doesn't exactly match the invoice amount (partial payment, small write-off), where the invoice was issued in a foreign currency, and where the customer pays in cash requiring rounding to the smallest coin denomination.

**Why this priority**: Getting money in and out of the books correctly — including the residual/write-off and currency-revaluation entries that keep the ledger balanced — is core bookkeeping; errors here directly corrupt the balance sheet and bank reconciliation.

**Independent Test**: Reconcile a payment that is €0.02 short of an invoice total against a write-off account, and separately reconcile a foreign-currency invoice against a payment booked at a different exchange rate; verify a write-off line and a realized exchange-gain/loss line are posted respectively, and that both invoices show as fully reconciled.

**Acceptance Scenarios**:

1. **Given** an open invoice and a payment that differs from its balance by a small amount, **When** the accountant reconciles them and designates a write-off account, **Then** a write-off line is posted to close the residual and both items are marked reconciled.
2. **Given** a payment and one or more open invoices for the same partner with matching or near-matching amounts and references, **When** the accountant opens the reconciliation screen, **Then** the system suggests likely matches instead of requiring manual invoice-ID entry.
3. **Given** an invoice issued in a foreign currency and later paid at a different exchange rate, **When** the payment is reconciled against the invoice, **Then** a realized exchange gain or loss entry is posted for the rate difference and both amounts (transaction currency and company currency) are correctly tracked.
4. **Given** open foreign-currency receivable/payable balances at period end, **When** the accountant runs a currency revaluation, **Then** an unrealized gain/loss adjustment is posted that does not affect realized results and can be reversed in the next period.
5. **Given** a cash payment configured with a cash-rounding profile, **When** the invoice total does not land on a payable denomination, **Then** the invoice is rounded per the configured strategy and the rounding difference is posted to the correct account.
6. **Given** a bank statement with a starting balance, an ending balance, and a set of transaction lines, **When** the accountant enters or imports it, **Then** each statement line can be reconciled against a payment or journal entry, and the statement is flagged incomplete if its computed running balance doesn't match its declared ending balance.

---

### User Story 3 - Journal entries that cannot be silently altered (Priority: P2)

An accountant (or auditor) needs assurance that once a journal entry is posted, neither its header nor its lines can be edited directly, that its number is never reused or skipped, that reversing it offers a review step, and that entries dated in a closed fiscal period cannot be created or edited without an explicit, scoped exception.

**Why this priority**: This is the integrity backbone that makes the reports in User Story 4 trustworthy and satisfies audit requirements, but it doesn't block someone from doing basic bookkeeping the way Stories 1–2 would — hence P2.

**Independent Test**: Post a journal entry, attempt to edit one of its lines directly, attempt to reset it to draft after enabling hash-chain mode, and attempt to post a new entry dated before the fiscal-year lock date — verify each is rejected with a way to reverse or seek an authorized exception instead.

**Acceptance Scenarios**:

1. **Given** a posted journal entry, **When** any user attempts to change an account, partner, debit, or credit value on one of its lines, **Then** the change is rejected exactly as a change to the entry's header would be.
2. **Given** two journals of the same type (e.g., two sales journals), **When** entries are posted in each, **Then** each journal maintains its own gap-free, non-reused numbering sequence.
3. **Given** a posted entry that is reset to draft and re-posted without changing its date relative to later entries, **When** it is re-posted, **Then** it keeps its original number rather than consuming a new one and leaving a gap.
4. **Given** an entry the accountant wants to reverse, **When** they trigger reversal, **Then** they can choose whether the reversal posts immediately or is left as a draft for review.
5. **Given** a journal with hash-chain (tamper-evident) mode enabled, **When** a posted entry in that journal is inspected, **Then** it carries a verifiable secure sequence number and hash, and any attempt to alter a secured entry or reset it to draft is rejected.
6. **Given** a company fiscal-year lock date, **When** a user attempts to create, post, or edit an entry dated on or before that date, **Then** the action is rejected unless an authorized user has granted a scoped, time-boxed lock exception for that user/journal/date range.

---

### User Story 4 - Reports an accountant can trust and drill into (Priority: P2)

An accountant runs the Trial Balance, General Ledger, Balance Sheet, Profit & Loss, Aged Receivables, Aged Payables, and Tax Report for a period and expects the same figures Odoo 19 Community would produce for the same data, with the ability to click from any reported figure down to the journal entries that produced it.

**Why this priority**: Reports are the accountant's primary deliverable, but they are only wrong because of upstream data/posting gaps (Stories 1–3); fixing them is meaningful once the underlying entries are trustworthy, so this follows rather than leads.

**Independent Test**: Post entries spanning two periods, then run the Trial Balance and General Ledger filtered to the second period only — verify both show the correct opening balance carried from the first period rather than starting from zero, and verify a report line can be clicked through to its source entries.

**Acceptance Scenarios**:

1. **Given** posted entries in a prior period and a report filtered to a later period, **When** the Trial Balance or General Ledger is generated, **Then** each account shows an opening balance reflecting all prior activity, with the filtered period's movement added on top.
2. **Given** any figure on the Trial Balance, Balance Sheet, Profit & Loss, or Aged Receivable/Payable report, **When** the accountant selects it, **Then** they can drill down to the underlying posted journal entries.
3. **Given** open customer/vendor balances with a mix of due and not-yet-due invoices, **When** the Aged Receivables/Payables report is run, **Then** not-yet-due balances appear in a distinct "current"/"not due" column separate from the first overdue bucket.
4. **Given** a company that has closed a prior fiscal year, **When** the Balance Sheet is generated for the current year, **Then** current-year earnings and prior-years' retained earnings are shown as separate figures.
5. **Given** taxes with report-grid tags configured on their repartition lines, **When** the accountant runs the Tax Report for a period, **Then** amounts are aggregated correctly by grid across all posted invoices and bills in that period.

---

### User Story 5 - Credit notes, debit notes, and down payments (Priority: P3)

An accountant needs to correct an already-issued invoice or bill in either direction (credit note to reduce, debit note to increase) and needs to record a customer down payment ahead of final invoicing.

**Why this priority**: These are lower-frequency but standard bookkeeping actions; credit notes already exist in dodoo, so this story is scoped to filling the debit-note and down-payment gaps.

**Independent Test**: Issue a debit note against a posted vendor bill and verify it links to and increases the amount owed on the original bill; separately record a down payment against a sales order/invoice and verify it appears as a distinct line deducted from the final invoice.

**Acceptance Scenarios**:

1. **Given** a posted vendor bill that undercharged the company, **When** the accountant creates a debit note against it, **Then** a new linked document is created that increases the amount owed, mirroring how a credit note decreases it.
2. **Given** a sales order or invoice, **When** the accountant records a customer down payment, **Then** it is tracked as a distinct line and deducted from the final invoice total.

---

### User Story 6 - Analytic accounting roll-up (Priority: P3)

An accountant tags journal items with analytic accounts (e.g., by department, project, or cost center) and runs an analytic report to see cost/revenue roll-ups by that dimension.

**Why this priority**: Confirmed present in Odoo 19 Community, but it is an overlay on top of correct core bookkeeping (Stories 1–4) rather than a blocker to it, and adoption varies by accountant — hence lowest priority while still in scope.

**Independent Test**: Create an analytic account, distribute a journal item's amount across one or more analytic accounts, and run an analytic report — verify the distributed amounts roll up correctly per analytic account.

**Acceptance Scenarios**:

1. **Given** one or more analytic accounts (optionally organized into plans), **When** the accountant assigns an analytic distribution to a journal item, **Then** the distribution is validated (e.g., percentages sum to 100%) and stored against real analytic accounts, not an arbitrary unvalidated value.
2. **Given** journal items with analytic distributions posted over a period, **When** an analytic report is run, **Then** amounts roll up correctly per analytic account/plan.

---

### Edge Cases

- What happens when a discount pushes a line's tax base to zero or the line becomes a full write-off — does tax computation and rounding still behave sensibly?
- How does the system handle a reconciliation write-off that itself needs to be reversed later?
- What happens when an entry is dated exactly on the lock date boundary (on the date itself, not just before it)?
- How does the system handle a foreign-currency invoice that is partially paid across multiple payments at different exchange rates before being fully reconciled?
- What happens when a user attempts to mark an off-balance or cash/credit-card-type account as reconcilable — is it rejected at the point of the attempt?
- How does the system handle concurrent posting attempts in the same journal, to guarantee no two entries receive the same sequence number and no number is skipped?
- What happens when a bank statement's declared ending balance doesn't match the sum of its starting balance and its lines — is it clearly flagged as incomplete rather than silently accepted?
- How does the aged-receivables bucketing behave for an invoice due exactly today (boundary between "current" and the first overdue bucket)?
- What happens when a lock-exception grant expires while an authorized edit is still in progress?
- How does an analytic distribution behave when it references an archived or deleted analytic account?

## Requirements *(mandatory)*

### Functional Requirements — Chart of Accounts

- **FR-001**: System MUST automatically classify each account into its account group by matching the group's code-prefix range, and MUST use that grouping when rolling up figures in financial reports.
- **FR-002**: System MUST prevent an account whose type is "off-balance" from being marked reconcilable, and MUST apply account-type-appropriate reconcile defaults/constraints consistently (e.g., cash and credit-card type accounts) rather than only forcing reconcile on receivable/payable accounts.

### Functional Requirements — Journals & Journal Entries

- **FR-003**: System MUST scope posted-entry numbering per journal, so two journals sharing the same move type never collide on or share a single number stream.
- **FR-004**: System MUST provide a distinct "Cancelled" state for journal entries, separate from "Draft," so a voided entry is distinguishable from one still being drafted.
- **FR-005**: System MUST NOT allocate a new sequence number when a previously posted entry is reset to draft and re-posted without a date change that would break sequence order; it MUST reuse the entry's original number.
- **FR-006**: System MUST let the user choose, at the point of reversing an entry, whether the reversal posts immediately or is created as a draft for review and date adjustment.

### Functional Requirements — Sequence Integrity, Locking, and Audit Trail

- **FR-007**: System MUST offer a per-journal, opt-in tamper-evident hash-chain mode for posted entries, exposing a verifiable secure sequence number and hash on each secured entry.
- **FR-008**: System MUST reject any direct modification to a posted journal entry's lines (account, partner, debit, credit, amounts), applying the same protection that already exists on the entry's header fields.
- **FR-009**: System MUST reject resetting a posted entry to draft when that entry has been secured by the hash chain or falls on or before an active lock date, not only when it has reconciled payment-term lines.

### Functional Requirements — Invoicing (Invoices, Bills, Credit Notes, Debit Notes, Down Payments)

- **FR-010**: System MUST support a per-line percentage or fixed-amount discount on invoice and bill lines.
- **FR-011**: System MUST provide a debit-note action that creates a new document linked to an existing posted invoice or bill, increasing the amount owed, analogous to how a credit note decreases it.
- **FR-012**: System MUST support recording a customer down payment as a distinct, trackable line that is deducted from the corresponding final invoice.

### Functional Requirements — Taxes

- **FR-013**: System MUST compute tax on the line's price net of any discount, not on the undiscounted price.
- **FR-014**: System MUST support tax-inclusive (price-included) pricing, extracting the tax portion from the gross price rather than adding tax on top of it.
- **FR-015**: System MUST make the tax rounding method ("round per line" vs. "round globally") configurable per company instead of hardcoding a single method.
- **FR-016**: System MUST support tax grids (report line tags on tax repartition lines) and a Tax Report that aggregates posted invoice/bill amounts by grid for a selected period.

### Functional Requirements — Payment Terms

- **FR-017**: System MUST validate that a payment term's installment lines sum to exactly 100%, rejecting terms that do not.
- **FR-018**: System MUST apply a payment term's early-payment-discount fields (percentage, discount-day window) when computing the amount due, exposing the discounted amount and its due date to the invoicing and payment flow.
- **FR-019**: System MUST compute the "days end of month, due on the Nth day" delay type using the configured target day of the resolved month, not the literal end of the current month.

### Functional Requirements — Payments and Reconciliation

- **FR-020**: System MUST support posting a write-off line to a designated account when reconciled amounts leave a residual difference, instead of requiring an exact amount match.
- **FR-021**: System MUST suggest likely reconciliation matches based on partner, amount, and reference/memo similarity, in addition to allowing manual selection.
- **FR-022**: System MUST track and use transaction-currency amounts (in addition to company-currency amounts) when determining reconciliation residuals and full-reconciliation status for foreign-currency lines.

### Functional Requirements — Multi-Currency

- **FR-023**: System MUST maintain a dated exchange-rate table per currency, populated by manual entry, so foreign-currency documents are converted using the rate applicable to their date. Automatic fetching of rates from an external provider is out of scope for this feature.
- **FR-024**: System MUST convert a foreign-currency document's transaction-currency amount into company-currency debit/credit using the applicable exchange rate at posting time.
- **FR-025**: System MUST post a realized exchange gain/loss entry when a foreign-currency invoice is reconciled against a payment booked at a different exchange rate.
- **FR-026**: System MUST provide a period-end unrealized currency gain/loss revaluation for open foreign-currency balances that does not affect realized results and is reversible in the following period.

### Functional Requirements — Bank and Cash

- **FR-027**: System MUST provide a bank statement entity, per bank account, with a starting balance, an ending balance, and a set of dated transaction lines, created via manual entry or structured (API-driven) bulk creation. Parsing of specific external bank file formats (e.g., CSV, OFX, CAMT.053) is out of scope for this feature.
- **FR-028**: System MUST validate statement continuity: a statement's starting balance must equal the prior statement's real ending balance, and the system must flag a statement as incomplete when its computed running balance does not match its declared ending balance.
- **FR-029**: System MUST let a user reconcile a bank statement line against one or more journal entries or payments.
- **FR-030**: System MUST support a configurable cash-rounding profile (rounding increment, rounding method, and a strategy for applying the rounding difference) for cash-paid invoices.

### Functional Requirements — Fiscal Periods

- **FR-031**: System MUST let a company set lock dates (an all-journals fiscal-year lock, a tax-return lock, and separate sales/purchases locks) after which entries dated on or before that date cannot be created, posted, or edited.
- **FR-032**: System MUST push a transaction's accounting date forward past a violated lock date (rather than silently accepting the back-dated entry or hard-blocking it with no path forward) and surface a warning to the user.
- **FR-033**: System MUST let an authorized user grant a time-boxed, scoped exception to a lock date for a specific user and/or journal, instead of requiring the lock itself to be rolled back to accommodate one correction.

### Functional Requirements — Financial Reports

- **FR-034**: Trial Balance and General Ledger MUST show each account's opening balance carried from all activity prior to the report's start date, with the filtered period's movement (and, for the General Ledger, its running balance) computed on top of that opening balance.
- **FR-035**: Trial Balance, General Ledger, Balance Sheet, Profit & Loss, and Aged Receivable/Payable reports MUST allow drill-down from any reported figure to the underlying posted journal entries.
- **FR-036**: Aged Receivable and Aged Payable reports MUST bucket not-yet-due balances into a distinct "current"/"not due" column, separate from the first overdue aging bucket.
- **FR-037**: Balance Sheet MUST report current-fiscal-year earnings separately from prior-years' retained (unallocated) earnings.

### Functional Requirements — Analytic Accounting

- **FR-038**: System MUST implement analytic accounts (optionally organized into plans) as real, referenceable records, and MUST validate an analytic distribution assigned to a journal item (e.g., that percentages sum to 100%) rather than accepting an arbitrary unvalidated value.
- **FR-039**: System MUST provide an analytic report that rolls up posted amounts by analytic account/plan for a selected period.

### Key Entities *(include if feature involves data)*

- **Account Group**: A code-prefix range used to auto-classify chart-of-accounts entries for report roll-up; relates one-to-many to Account.
- **Currency Rate**: A currency's exchange rate as of a specific date, manually entered, used to convert foreign-currency documents into company-currency amounts.
- **Bank Statement / Bank Statement Line**: A dated record of a bank account's starting balance, ending balance, and individual transaction lines (entered manually or created via a structured API), each of which can be reconciled against payments or journal entries.
- **Cash Rounding Profile**: A configurable rounding increment, method, and application strategy used on cash-settled invoices.
- **Lock Date / Lock Exception**: Company-level dates (fiscal-year, tax, sales, purchases) before which postings are restricted, and scoped, time-boxed exceptions that authorized users may grant against them.
- **Tax Grid (Report Line Tag)**: A tag attached to a tax's repartition lines that determines which line of the Tax Report an amount contributes to.
- **Debit Note**: A document linked to an existing posted invoice or bill that increases the amount owed, mirroring a credit note.
- **Down Payment**: A distinct, trackable invoice line representing an advance payment, deducted from a subsequent final invoice.
- **Reconciliation Write-off**: A posting that closes a residual difference between reconciled amounts against a designated account.
- **Analytic Account / Analytic Plan / Analytic Distribution**: Dimensions (e.g., department, project, cost center) that journal items can be distributed across, validated and rolled up in analytic reporting.

### Security Requirements *(include if feature touches auth, data, or external I/O)*

- **SEC-001**: System MUST continue to enforce that only permitted roles can post, reverse, or reset journal entries to draft; the new "Cancelled" state and lock-exception mechanism MUST NOT bypass existing role-based access checks.
- **SEC-002**: Lock-exception grants MUST be scoped to a specific user and/or journal and MUST expire automatically at their configured end date; an expired exception MUST have no further effect.
- **SEC-003**: System MUST log which user granted a lock exception, to whom, and for what date range, so the grant itself is auditable.

### Performance Requirements

- **PERF-001**: Adding opening-balance computation to Trial Balance and General Ledger MUST NOT regress report generation time beyond current levels for equivalent data volumes; opening balances MUST be computed via aggregate queries, not by iterating all historical entries row-by-row per report run.
- **PERF-002**: Reconciliation match-suggestion MUST return candidates for a typical partner's open items without noticeable delay in interactive use.
- **PERF-003**: No known regressions permitted in existing accounting test suites or report response times; equivalent benchmarks MUST be re-run for any touched report or posting path.
- **PERF-004**: Looking up the exchange rate applicable to a given currency and date MUST return without noticeable delay in interactive use (invoice/payment posting is on this path for every foreign-currency document).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every functional area audited (chart of accounts, journals, invoicing, taxes, payment terms, reconciliation, multi-currency, bank/cash, fiscal periods, reports, analytic accounting, audit trail), an accountant can complete the equivalent Odoo 19 Community workflow in dodoo end-to-end (create → post → appears correctly in reports) using the same input data.
- **SC-002**: Every gap and divergence recorded in the Audit Summary above is resolved: 100% of previously-missing capabilities are present and usable, and 100% of previously-incorrect calculations produce results matching the reference implementation for equivalent test data.
- **SC-003**: For a representative invoice with a per-line discount, a price-included tax, and a multi-installment payment term with an early-payment discount, dodoo's computed subtotal, tax, total, and due-date schedule match Odoo 19 Community's output exactly (to the configured currency precision) for the same inputs.
- **SC-004**: For a foreign-currency invoice reconciled against a payment at a different exchange rate, the realized exchange gain/loss entry amount matches the reference calculation exactly.
- **SC-005**: A posted journal entry's lines cannot be altered by any user action other than reversal or a new entry, verified by attempting direct edits and observing rejection in 100% of attempted cases.
- **SC-006**: Trial Balance and General Ledger figures for a period-filtered report match the reference implementation's opening-balance-inclusive figures, verified against at least one multi-period test dataset.
- **SC-007**: No existing, already-correct accounting behavior regresses: the full pre-existing accounting test suite continues to pass unchanged in scope.

## Assumptions

- The reference implementation for all "correct" behavior is `../odoo-19.0/addons/account` (Odoo 19.0 Community edition) as it exists in the checked-out source; where Community behavior itself varies by localization, the generic (non-localized) Community behavior is the target.
- Fixed-asset depreciation management and budgeting are out of scope, per the feature description, because they are absent from the Community reference — no such capability will be introduced.
- Analytic accounting is in scope because it is confirmed present in Odoo 19 Community core (`account` + `analytic` addons), not an Enterprise-only feature.
- Where a gap requires a genuinely new data concept (e.g., bank statements, currency rates, lock exceptions, analytic accounts), the new entity's shape follows the reference implementation's model closely enough to reproduce its behavior, without requiring pixel-identical UI.
- Existing dodoo integration points (`stock_account` for inventory valuation, `product` for pricing/UoM) are treated as inputs to the accounting entries they feed; this feature corrects how `account` consumes and posts those inputs, not the valuation/pricing logic itself, unless a specific finding above says otherwise.
- "Debit note" and "down payment" are treated as core accounting capabilities to complete per the audit findings, even though in Odoo they are delivered via a small companion addon (`account_debit_note`) and sale-flow integration respectively; the requirement here is the accounting-side capability (create a linked, amount-increasing document; track a distinct advance-payment line), not any dependency on the `sale` app.
- Per the Clarifications above, currency-rate acquisition is manual-entry-only (no external rate-provider integration) and bank statement creation is manual/API-only (no specific file-format import parser); both remain natural, additive extensions of the data model introduced here and can be layered on in a future feature without rework.
