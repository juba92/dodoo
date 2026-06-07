# Implementation Plan: Accounting Module

**Branch**: `003-accounting` | **Date**: 2026-06-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-accounting/spec.md`

## Summary

Build a double-entry accounting addon (`dodoo/addons/account/`) modelled on Odoo 19.0's account module. Core engine: `account.move` (journal entries) with a strict `SUM(debit) == SUM(credit)` posting gate, `account.move.line` for individual postings, reconciliation via `account.partial.reconcile` / `account.full.reconcile`, and five financial report queries. All entities are exposed through the existing JSON-RPC `execute_kw` interface; no UI changes required. Prerequisites: add `res.partner`, `res.company`, `res.currency` to the base addon and add `Selection`, `Monetary`, `Json` field types to `dodoo/core/fields.py`.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, SQLAlchemy Core (async), asyncpg, Pydantic v2 — all existing; no new packages required

**Storage**: PostgreSQL via asyncpg. Monetary columns use `NUMERIC(20, 6)` (not FLOAT) to prevent floating-point errors on financial calculations.

**Testing**: pytest + pytest-asyncio (existing pattern); 80% unit coverage enforced; 100% branch coverage on balance constraint, posting gate, reconciliation engine, and tax computation

**Target Platform**: Linux server (single-process FastAPI)

**Project Type**: Dodoo addon (self-contained Python package under `dodoo/addons/account/`)

**Performance Goals**:
- PERF-001: Single record retrieval < 500 ms at normal load
- PERF-002: Financial reports (Trial Balance, P&L, Balance Sheet) < 5 s for 50,000 posted lines
- PERF-003: Balance constraint check adds < 100 ms overhead vs unvalidated write

**Constraints**: Single functional currency per company; no multi-currency exchange logic; single company context; no PDF generation; no bank statement import

**Scale/Scope**: SME scale — up to 50,000 posted journal lines, single user session

## Constitution Check

- [X] **I. Code Quality**: Black + ruff enforced (existing project tooling); zero linting errors on merge
- [X] **II. Testing**: pytest-asyncio; ≥ 80% unit coverage; 100% critical paths (balance check, posting, reconciliation, tax computation); integration tests hit real PostgreSQL
- [X] **III. Security**: SEC-001–004 in spec; OWASP Top 10 reviewed — parameterized queries only (SQLAlchemy Core), session auth on all routes, monetary input validation at API boundary, company isolation on reconciliation
- [X] **IV. Performance**: PERF-001–003 defined above; benchmark strategy: pytest-benchmark on posting and report queries against seeded 50k-line dataset
- [X] **V. Documentation**: 5 ADRs filed (see ADR section below); inline comments explain WHY only; no docstring bloat
- [X] **VI. Accessibility**: ACC-001 (currency formatting with symbol + separators) and ACC-002 (debit/credit distinguishable by label+position not color) implemented; no UI screens in this module beyond generic list/form
- [X] **VII. Dependencies**: Zero new packages — existing stack (SQLAlchemy, asyncpg, FastAPI, Pydantic) covers all needs; no CVE audit burden
- [X] **VIII. CI/CD**: No CI pipeline exists in dodoo yet — noted as out of scope for this module; gates enforced locally via pre-commit Black+ruff
- [X] **IX. Observability**: OBS-001 — every state transition emits a structured JSON log entry with move_id, transition, user_id, utc_timestamp via `dodoo.core.logging`

## Architecture Decision Records

**ADR-001: NUMERIC(20,6) for monetary columns**
- Decision: All debit, credit, amount fields use `NUMERIC(20, 6)` PostgreSQL type, Python `Decimal`.
- Rationale: FLOAT cannot represent 0.1 exactly; financial calculations require exact decimal arithmetic. Odoo uses `Float(digits=(16,2))` but backed by PostgreSQL FLOAT — a known source of rounding bugs. We use NUMERIC to eliminate them.
- Alternative rejected: Python `float` + rounding — insufficient for multi-line tax computation.

**ADR-002: Application-level sequence counter table**
- Decision: A dedicated `account_sequence` table with columns `(prefix VARCHAR, year INTEGER, last_number INTEGER)` and row-level `SELECT ... FOR UPDATE` to generate move names atomically.
- Rationale: PostgreSQL native SEQUENCE objects require DDL per journal per year. The counter table approach requires no DDL at runtime and is portable. Row-level lock ensures no duplicate sequence numbers under concurrency (FR-013 edge case).
- Alternative rejected: PostgreSQL SEQUENCE objects — too much DDL complexity; application-level counter with optimistic locking — insufficient under concurrent conditions.

**ADR-003: `round_globally` tax computation**
- Decision: Tax amounts are summed across all product lines first, then rounded once to the currency's decimal places.
- Rationale: `round_per_line` produces per-line rounded amounts whose sum may differ from the rounded total, causing balance constraint violations on invoices with many lines. `round_globally` matches Odoo's `tax_calculation_rounding_method` default and eliminates this class of error.
- Alternative rejected: `round_per_line` — causes penny imbalances on multi-line invoices.

**ADR-004: Reports as JSON-RPC callable model methods**
- Decision: Financial reports are implemented as class methods on virtual models (e.g., `AccountReportTrialBalance`) callable via `execute_kw` with method `get_report`. They return a list of dicts that the existing web UI list view can render.
- Rationale: The existing web UI calls `execute_kw` for all data. Adding report endpoints as custom REST routes would require UI changes. Virtual model methods fit the existing pattern with zero UI modification.
- Alternative rejected: Custom REST endpoints — require UI changes; ORM stored views — no migration path in current stack.

**ADR-005: base addon extended with res.partner / res.company / res.currency**
- Decision: `res.partner`, `res.company`, `res.currency` models are added to `dodoo/addons/base/models/` as prerequisites for the accounting module.
- Rationale: These are fundamental business objects that belong in base (matching Odoo). Adding them in the account addon would create circular dependency potential and break the module separation principle.
- Alternative rejected: Defining them in the account addon — violates single-responsibility; would need to be moved later anyway.

## Project Structure

### Documentation (this feature)

```text
specs/003-accounting/
├── plan.md              # This file
├── research.md          # Technical decisions (generated below)
├── data-model.md        # Full entity model
├── quickstart.md        # Validation guide
├── contracts/           # JSON-RPC method contracts
└── tasks.md             # Task breakdown (speckit-tasks output)
```

### Source Code

```text
dodoo/core/
└── fields.py                        # ADD: Selection, Monetary, Json field types

dodoo/addons/base/models/
├── res_currency.py                  # NEW: res.currency (code, name, symbol, rounding)
├── res_company.py                   # NEW: res.company (name, currency_id)
└── res_partner.py                   # NEW: res.partner (name, company_id, email, phone, vat)

dodoo/addons/account/
├── __manifest__.py                  # application=True, depends=['base']
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── account_account.py           # account.account + account.account.group
│   ├── account_journal.py           # account.journal + account_sequence table
│   ├── account_move.py              # account.move (action_post, reset_to_draft, reverse)
│   ├── account_move_line.py         # account.move.line
│   ├── account_tax.py               # account.tax + account.tax.group + account.tax.repartition.line
│   ├── account_fiscal_position.py   # account.fiscal.position + mapping lines
│   ├── account_payment_term.py      # account.payment.term + account.payment.term.line
│   ├── account_payment.py           # account.payment
│   ├── account_reconcile.py         # account.partial.reconcile + account.full.reconcile
│   └── account_report.py            # Virtual report models (trial balance, GL, P&L, BS, aged)
├── http/
│   └── __init__.py                  # REST routes: /account/action_post, /account/reconcile, etc.
└── data/
    ├── __init__.py
    └── chart_of_accounts.py         # ~25-account default CoA + seed journals
```

## Complexity Tracking

No constitution violations. All choices are simplest-path implementations.

## Detailed Technical Design

### New Field Types (dodoo/core/fields.py)

| Type | SA Column | Python Type | Notes |
|------|-----------|-------------|-------|
| `Selection(choices)` | `VARCHAR(64)` | `str` | choices = list of (value, label) pairs |
| `Monetary()` | `NUMERIC(20, 6)` | `Decimal` | always non-negative enforced at ORM; default 0 |
| `Json()` | `JSONB` | `dict` | for analytic_distribution |

### Base Models to Add

**res.currency**: `code` (Char 3, required), `name` (Char 64), `symbol` (Char 8), `rounding` (Integer, default 2 = decimal places), `active` (Boolean)

**res.company**: `name` (Char 128, required), `currency_id` (Many2one `res.currency`, required), `partner_id` (Many2one `res.partner`)

**res.partner**: `name` (Char 256, required), `company_id` (Many2one `res.company`), `email` (Char 256), `phone` (Char 64), `vat` (Char 32), `active` (Boolean, default True), `is_company` (Boolean, default False), `property_account_receivable_id` (Many2one `account.account`), `property_account_payable_id` (Many2one `account.account`), `property_payment_term_id` (Many2one `account.payment.term`), `property_supplier_payment_term_id` (Many2one `account.payment.term`)

### Balance Constraint Implementation

On `action_post`, execute a single SQL query before any state change:

```sql
SELECT move_id,
       ROUND(SUM(debit)::NUMERIC, 2)  AS total_debit,
       ROUND(SUM(credit)::NUMERIC, 2) AS total_credit
FROM account_move_line
WHERE move_id = :move_id
  AND display_type NOT IN ('line_section', 'line_note')
GROUP BY move_id
HAVING ROUND(SUM(debit)::NUMERIC, 2) != ROUND(SUM(credit)::NUMERIC, 2)
```

If rows returned → raise `ValidationError` with imbalance amount.

### Sequence Generation

```sql
-- Table (created in account_journal migration)
CREATE TABLE IF NOT EXISTS account_sequence (
    prefix  VARCHAR(32) NOT NULL,
    year    INTEGER     NOT NULL,
    last_no INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (prefix, year)
);
```

On `action_post`, within a transaction:
```sql
INSERT INTO account_sequence (prefix, year, last_no)
VALUES (:prefix, :year, 1)
ON CONFLICT (prefix, year) DO UPDATE
  SET last_no = account_sequence.last_no + 1
RETURNING last_no;
```
Format result as `{PREFIX}/{YEAR}/{last_no:04d}`.

### Tax Computation Pipeline (round_globally)

```
For each product line:
    raw_tax_amounts[tax_id] += line.price_unit * line.quantity * tax.amount / 100

For each tax_id:
    rounded_amount = round(raw_tax_amounts[tax_id], currency.rounding)
    → generate tax move line with this amount

Verify total_tax_lines match the rounded total (adjust last line by ±0.01 if needed)
```

### Reconciliation Engine

```
partial_reconcile(debit_line_id, credit_line_id, amount):
  1. Validate both lines are posted, on reconcilable accounts, same company
  2. Validate amount ≤ min(debit_line.amount_residual, abs(credit_line.amount_residual))
  3. INSERT INTO account_partial_reconcile
  4. Recompute residuals for both lines
  5. Check if all lines in the group net to zero → if yes, INSERT account_full_reconcile
     and UPDATE all participating lines SET full_reconcile_id = new_id
```

### Report Queries

**Trial Balance** (PERF-002 target):
```sql
SELECT a.code, a.name, a.account_type,
       ROUND(SUM(l.debit), 2)   AS total_debit,
       ROUND(SUM(l.credit), 2)  AS total_credit,
       ROUND(SUM(l.balance), 2) AS net_balance
FROM account_move_line l
JOIN account_account a ON a.id = l.account_id
JOIN account_move m ON m.id = l.move_id
WHERE m.state = 'posted'
  AND m.date BETWEEN :date_from AND :date_to
  AND l.display_type NOT IN ('line_section', 'line_note')
GROUP BY a.id, a.code, a.name, a.account_type
ORDER BY a.code
```

Index required: `(move_id, display_type)` on `account_move_line`; `(state, date)` on `account_move`.

### Default Chart of Accounts (25 accounts)

Seeded at install time via `data/chart_of_accounts.py`. One account per type plus essentials:

| Code | Name | Type |
|------|------|------|
| 1000 | Accounts Receivable | asset_receivable |
| 1010 | Cash | asset_cash |
| 1020 | Bank | asset_cash |
| 1100 | Prepaid Expenses | asset_prepayments |
| 1200 | Inventory | asset_current |
| 1500 | Equipment | asset_fixed |
| 1600 | Accumulated Depreciation | asset_non_current |
| 2000 | Accounts Payable | liability_payable |
| 2010 | Credit Card | liability_credit_card |
| 2100 | Accrued Liabilities | liability_current |
| 2200 | Long-term Debt | liability_non_current |
| 2500 | VAT Collected | liability_current |
| 2510 | VAT Deductible | asset_current |
| 3000 | Share Capital | equity |
| 3100 | Retained Earnings | equity_unaffected |
| 4000 | Revenue | income |
| 4100 | Other Income | income_other |
| 5000 | Cost of Goods Sold | expense_direct_cost |
| 5100 | Operating Expenses | expense |
| 5200 | Other Expenses | expense_other |
| 5300 | Depreciation | expense_depreciation |
| 9000 | Off-Balance Memo | off_balance |

Seeded journals: Customer Invoices (sale, prefix INV), Vendor Bills (purchase, prefix BILL), Cash (cash, prefix CSH), Bank (bank, prefix BNK), Miscellaneous (general, prefix MISC).

Default company: "My Company" with EUR as functional currency.
