# Research: Accounting Module

**Date**: 2026-06-07 | **Branch**: `003-accounting`

## 1. Monetary Precision

**Decision**: `NUMERIC(20, 6)` PostgreSQL column + Python `decimal.Decimal`

**Rationale**: FLOAT cannot represent 0.1 or 0.01 exactly. Accounting requires exact arithmetic. PostgreSQL NUMERIC stores values with exact precision up to 131072 digits before the decimal. Six decimal places accommodates currencies with up to 6 significant decimals (e.g. KWD = 3, BTC = 8, but we cap at 6 for SME use). Python's `Decimal` type maps directly.

**Alternatives considered**:
- Python `float` + rounding at display time — fails silently on multi-line tax summation; rejected
- Integer pence storage (multiply by 100) — loses multi-currency generality; rejected

**References**: Odoo uses `Float(digits=(16,2))` but this is stored as PostgreSQL FLOAT8, a documented source of rounding bugs in their community issue tracker.

---

## 2. Sequence Generation for Move Names

**Decision**: Application-level `account_sequence` counter table with `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`

**Rationale**: PostgreSQL native `SEQUENCE` objects require one DDL statement per (journal, year) combination. Creating sequences dynamically at runtime requires DDL privileges on the app DB user, which violates the least-privilege principle. The counter table approach requires only DML privileges and handles concurrency via PostgreSQL's atomic upsert with `RETURNING`.

**Algorithm**:
```sql
INSERT INTO account_sequence (prefix, year, last_no) VALUES (:p, :y, 1)
ON CONFLICT (prefix, year) DO UPDATE SET last_no = account_sequence.last_no + 1
RETURNING last_no;
```
The upsert is atomic per row — no explicit lock needed. Under concurrent sessions, one wins and the other retries implicitly via the conflict path.

**Alternatives considered**:
- PostgreSQL `SEQUENCE` objects — requires DDL at runtime, DDL privilege; rejected
- SELECT + UPDATE with `FOR UPDATE` lock — two-query approach; more code, same correctness; rejected
- Redis atomic counter — external dependency; rejected

---

## 3. Tax Computation: round_globally

**Decision**: Sum all raw tax amounts across lines, round the total once

**Rationale**: Odoo's own `account.tax.compute_all()` supports both `round_per_line` and `round_globally`. The company setting `tax_calculation_rounding_method` defaults to `round_globally`. On a 3-line invoice where each line's tax is €6.666…, `round_per_line` yields 3 × €6.67 = €20.01 but the expected total tax is €20.00, causing a 1-cent imbalance that violates the balance constraint. `round_globally` sums to €20.00 and rounds once.

**Implementation**: Collect `{tax_id: sum_of_raw_amounts}`, round each sum to `currency.rounding` decimal places. If rounding adjustments cause the total of tax lines to differ from the rounded total by ±1 unit, absorb the difference into the largest tax line.

**References**: Odoo 19.0 `addons/account/models/account_tax.py` line 1374 (`rounding_method='round_globally'`).

---

## 4. Report Access Pattern

**Decision**: Virtual model classes with `get_report(params)` method callable via `execute_kw`

**Rationale**: The existing web UI calls all data via JSON-RPC `execute_kw`. Adding custom REST endpoints would require JavaScript changes to the SPA. Virtual models that expose a `get_report` method fit the existing pattern — the SPA can call `execute_kw('account.report.trial_balance', 'get_report', [[]], {date_from, date_to})` and render the result with the generic list view.

**Report models**:
- `account.report.trial_balance` → `get_report({date_from, date_to})`
- `account.report.general_ledger` → `get_report({account_id, date_from, date_to})`
- `account.report.profit_loss` → `get_report({date_from, date_to})`
- `account.report.balance_sheet` → `get_report({date})`
- `account.report.aged_receivable` → `get_report({date})`
- `account.report.aged_payable` → `get_report({date})`

**Alternatives considered**:
- Custom REST endpoints — requires SPA changes; rejected
- PostgreSQL views + ORM models — no filtering capability without parameter injection; rejected

---

## 5. Base Model Prerequisites

**Decision**: Add `res.currency`, `res.company`, `res.partner` to `dodoo/addons/base/`

**Rationale**: These are used by `res.users` (implicitly via company_id on most business objects), are required before any accounting entity can reference them, and belong in the base addon per Odoo's module architecture. Adding them in the account addon would create a layer violation (base depending on account is fine; account depending on new base-level entities it defines itself is circular in intent).

**res.currency fields**: code (VARCHAR 3), name, symbol, rounding (int = decimal places, default 2), active
**res.company fields**: name, currency_id (FK res.currency), partner_id (FK res.partner, optional)
**res.partner fields**: name, company_id (FK res.company), email, phone, vat, active, is_company, property_account_receivable_id (FK account.account, nullable), property_account_payable_id (FK account.account, nullable), property_payment_term_id (FK account.payment.term, nullable), property_supplier_payment_term_id (FK account.payment.term, nullable)

**Note on circular dependency**: res.partner references account.account and account.payment.term. In PostgreSQL, the FK columns are added via ALTER TABLE after both tables exist (migration runner adds columns column-by-column, so the column can be added once the referenced table is created). The migration order in the installer must be: res.currency → res.company → res.partner (base columns only) → account models → res.partner (accounting FK columns via ALTER TABLE).

**Alternatives considered**:
- Define in account addon — violates base/addon separation; rejected
- Stub tables without FK enforcement — loses referential integrity; rejected

---

## 6. Database Indexes for PERF-002

Required indexes to achieve 5-second report time on 50,000 posted lines:

```sql
-- Most critical: filter by posted state + date range
CREATE INDEX idx_account_move_state_date ON account_move (state, date);

-- Join from move_line to move
CREATE INDEX idx_account_move_line_move_id ON account_move_line (move_id);

-- Filter out non-accounting lines in all reports
CREATE INDEX idx_account_move_line_display_type ON account_move_line (display_type);

-- Aged reports: filter by account_type on account
CREATE INDEX idx_account_account_type ON account_account (account_type);

-- Reconciliation residual queries
CREATE INDEX idx_account_move_line_account_reconciled ON account_move_line (account_id, reconciled);
```

---

## 7. Structured Logging (OBS-001)

Every state transition uses `dodoo.core.logging` (existing) with a structured JSON payload:

```python
_log.info(
    "account.move state transition",
    extra={
        "move_id": move_id,
        "transition": "draft_to_posted",  # or posted_to_draft, reconcile, unreconcile
        "user_id": env.uid,
        "utc_timestamp": datetime.utcnow().isoformat(),
        "move_name": name,
    }
)
```

The existing `dodoo.core.logging` module already outputs JSON-formatted log entries.
