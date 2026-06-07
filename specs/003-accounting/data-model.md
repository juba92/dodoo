# Data Model: Accounting Module

**Date**: 2026-06-07 | **Branch**: `003-accounting`

---

## Prerequisites (added to base addon)

### res.currency

Table: `res_currency`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| code | VARCHAR(3) | NOT NULL UNIQUE | ISO 4217 e.g. EUR, USD |
| name | VARCHAR(64) | NOT NULL | e.g. "Euro" |
| symbol | VARCHAR(8) | | e.g. "€" |
| rounding | INTEGER | NOT NULL DEFAULT 2 | decimal places |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

### res.company

Table: `res_company`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(128) | NOT NULL | |
| currency_id | INTEGER | FK res_currency NOT NULL | functional currency |
| partner_id | INTEGER | FK res_partner NULL | company's own partner |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

### res.partner

Table: `res_partner`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| company_id | INTEGER | FK res_company NULL | |
| email | VARCHAR(256) | | |
| phone | VARCHAR(64) | | |
| vat | VARCHAR(32) | | tax ID |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | soft delete |
| is_company | BOOLEAN | NOT NULL DEFAULT FALSE | |
| property_account_receivable_id | INTEGER | FK account_account NULL | default AR account |
| property_account_payable_id | INTEGER | FK account_account NULL | default AP account |
| property_payment_term_id | INTEGER | FK account_payment_term NULL | default customer term |
| property_supplier_payment_term_id | INTEGER | FK account_payment_term NULL | default vendor term |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

---

## Core Field Types (new in dodoo/core/fields.py)

| Dodoo Type | SA Column | Python type | Notes |
|-----------|-----------|-------------|-------|
| `Selection(choices)` | `VARCHAR(64)` | `str` | validated against choices list |
| `Monetary()` | `NUMERIC(20, 6)` | `Decimal` | non-negative enforced at ORM layer |
| `Json()` | `JSONB` | `dict` | nullable; for analytic_distribution |

---

## Accounting Entities

### account.account (Chart of Accounts)

Table: `account_account`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| code | VARCHAR(64) | NOT NULL | unique per company |
| name | VARCHAR(256) | NOT NULL | |
| account_type | VARCHAR(64) | NOT NULL | see enum below |
| internal_group | VARCHAR(32) | computed | asset/liability/equity/income/expense |
| reconcile | BOOLEAN | NOT NULL DEFAULT FALSE | must be TRUE for receivable/payable |
| currency_id | INTEGER | FK res_currency NULL | optional foreign-currency lock |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | soft delete |
| company_id | INTEGER | FK res_company NOT NULL | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**Unique constraint**: `(code, company_id)`

**account_type enum** (18 values):
`asset_receivable`, `asset_cash`, `asset_current`, `asset_non_current`, `asset_prepayments`, `asset_fixed`, `liability_payable`, `liability_credit_card`, `liability_current`, `liability_non_current`, `equity`, `equity_unaffected`, `income`, `income_other`, `expense`, `expense_other`, `expense_depreciation`, `expense_direct_cost`, `off_balance`

**internal_group** (computed from prefix):
- `asset_*` → `asset`
- `liability_*` → `liability`
- `equity*` → `equity`
- `income*` → `income`
- `expense*` → `expense`
- `off_balance` → `off_balance`

**Business rules**:
- `account_type IN (asset_receivable, liability_payable)` → ENFORCE `reconcile = TRUE` on write
- `account_type = off_balance` → PREVENT tax assignment (FR-025)

---

### account.account.group

Table: `account_account_group`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| code_prefix_start | VARCHAR(64) | NOT NULL | inclusive lower bound |
| code_prefix_end | VARCHAR(64) | NOT NULL | inclusive upper bound |
| parent_id | INTEGER | FK account_account_group NULL | for nested groups |
| company_id | INTEGER | FK res_company NOT NULL | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

Auto-assignment: account belongs to the group where `code_prefix_start ≤ code ≤ code_prefix_end`.

---

### account.journal

Table: `account_journal`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| code | VARCHAR(10) | NOT NULL | short prefix (INV, BILL, BNK, CSH, MISC) |
| type | VARCHAR(32) | NOT NULL | sale/purchase/cash/bank/general |
| default_account_id | INTEGER | FK account_account NULL | |
| suspense_account_id | INTEGER | FK account_account NULL | bank/cash only |
| currency_id | INTEGER | FK res_currency NULL | optional journal currency |
| company_id | INTEGER | FK res_company NOT NULL | |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**type enum**: `sale`, `purchase`, `cash`, `bank`, `general`

**Journal/move-type compatibility** (enforced on action_post):
- `sale` → `out_invoice`, `out_refund` only
- `purchase` → `in_invoice`, `in_refund` only
- `cash`, `bank` → payments only
- `general` → `entry` only

---

### account_sequence (sequence counter — not exposed as ORM model)

Table: `account_sequence`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| prefix | VARCHAR(32) | PK part | journal code e.g. INV |
| year | INTEGER | PK part | e.g. 2026 |
| last_no | INTEGER | NOT NULL DEFAULT 0 | atomically incremented |

---

### account.move (Journal Entry)

Table: `account_move`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(64) | | assigned on post e.g. INV/2026/0001 |
| move_type | VARCHAR(32) | NOT NULL DEFAULT 'entry' | see enum |
| state | VARCHAR(32) | NOT NULL DEFAULT 'draft' | draft/posted/cancel |
| payment_state | VARCHAR(32) | NOT NULL DEFAULT 'not_paid' | invoice moves only |
| journal_id | INTEGER | FK account_journal NOT NULL | |
| company_id | INTEGER | FK res_company NOT NULL | |
| currency_id | INTEGER | FK res_currency NOT NULL | |
| partner_id | INTEGER | FK res_partner NULL | |
| date | DATE | NOT NULL | accounting date |
| invoice_date | DATE | | document date (invoices) |
| invoice_date_due | DATE | | earliest due date (computed) |
| invoice_payment_term_id | INTEGER | FK account_payment_term NULL | |
| ref | VARCHAR(256) | | vendor ref / payment ref |
| narration | TEXT | | notes |
| amount_untaxed | NUMERIC(20,6) | NOT NULL DEFAULT 0 | computed |
| amount_tax | NUMERIC(20,6) | NOT NULL DEFAULT 0 | computed |
| amount_total | NUMERIC(20,6) | NOT NULL DEFAULT 0 | computed |
| amount_residual | NUMERIC(20,6) | NOT NULL DEFAULT 0 | computed unpaid balance |
| reversed_entry_id | INTEGER | FK account_move NULL | for credit notes |
| posted_before | BOOLEAN | NOT NULL DEFAULT FALSE | guards sequence reuse |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**move_type enum**: `entry`, `out_invoice`, `out_refund`, `in_invoice`, `in_refund`, `out_receipt`, `in_receipt`

**state transitions**:
```
draft → posted   : action_post() — validates balance, assigns name
posted → draft   : action_reset_to_draft() — blocked if any reconciliation exists
posted → cancel  : action_reverse() — creates mirror entry, sets reversed_entry_id
```

**payment_state enum** (invoice moves only): `not_paid`, `partial`, `in_payment`, `paid`, `reversed`, `blocked`

---

### account.move.line (Journal Entry Line)

Table: `account_move_line`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| move_id | INTEGER | FK account_move NOT NULL ON DELETE CASCADE | |
| sequence | INTEGER | NOT NULL DEFAULT 10 | display order |
| account_id | INTEGER | FK account_account NOT NULL | |
| partner_id | INTEGER | FK res_partner NULL | required on AR/AP accounts |
| name | VARCHAR(256) | | description |
| date | DATE | NOT NULL | copied from move.date |
| display_type | VARCHAR(32) | NOT NULL DEFAULT 'product' | see enum |
| debit | NUMERIC(20,6) | NOT NULL DEFAULT 0 | ≥ 0 |
| credit | NUMERIC(20,6) | NOT NULL DEFAULT 0 | ≥ 0 |
| balance | NUMERIC(20,6) | NOT NULL DEFAULT 0 | = debit - credit (stored) |
| amount_currency | NUMERIC(20,6) | | nullable; foreign currency amount |
| currency_id | INTEGER | FK res_currency NULL | nullable; foreign currency |
| tax_base_amount | NUMERIC(20,6) | NOT NULL DEFAULT 0 | base for tax lines |
| analytic_distribution | JSONB | | cost allocation JSON |
| reconciled | BOOLEAN | NOT NULL DEFAULT FALSE | computed |
| full_reconcile_id | INTEGER | FK account_full_reconcile NULL | |
| amount_residual | NUMERIC(20,6) | NOT NULL DEFAULT 0 | computed |
| tax_line_id | INTEGER | FK account_tax NULL | for tax lines |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**display_type enum**: `product`, `tax`, `payment_term`, `line_section`, `line_note`

**Business rules**:
- `debit >= 0`, `credit >= 0`, NOT (debit > 0 AND credit > 0)
- `display_type IN (asset_receivable, liability_payable)` → partner_id NOT NULL
- `display_type IN (line_section, line_note)` → excluded from all amount computation
- `tax` and `payment_term` lines: auto-generated; blocked from direct user creation via API

**Junction table** (tax_ids on product lines): `account_move_line_tax_rel (line_id, tax_id)`

**Indexes**:
- `(move_id)`, `(account_id, reconciled)`, `(move_id, display_type)`

---

### account.tax

Table: `account_tax`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| type_tax_use | VARCHAR(32) | NOT NULL | sale/purchase/none |
| amount_type | VARCHAR(32) | NOT NULL | percent/fixed/division/group |
| amount | NUMERIC(20,6) | NOT NULL DEFAULT 0 | e.g. 20.0 for 20% |
| price_include | BOOLEAN | NOT NULL DEFAULT FALSE | tax included in price |
| include_base_amount | BOOLEAN | NOT NULL DEFAULT FALSE | cascading |
| tax_group_id | INTEGER | FK account_tax_group NULL | |
| country_id | INTEGER | NULL | country scope |
| company_id | INTEGER | FK res_company NOT NULL | |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**Junction table** (group children): `account_tax_filiation_rel (parent_id, child_id)`

**amount_type enum**: `percent`, `fixed`, `division`, `group`

---

### account.tax.group

Table: `account_tax_group`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| sequence | INTEGER | NOT NULL DEFAULT 10 | display order |
| company_id | INTEGER | FK res_company NOT NULL | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

---

### account.tax.repartition.line

Table: `account_tax_repartition_line`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| tax_id | INTEGER | FK account_tax NOT NULL ON DELETE CASCADE | |
| document_type | VARCHAR(16) | NOT NULL | invoice/refund |
| repartition_type | VARCHAR(16) | NOT NULL | base/tax |
| factor_percent | NUMERIC(20,6) | NOT NULL DEFAULT 100 | 100 normal, -100 reverse charge |
| account_id | INTEGER | FK account_account NULL | NULL for base lines |
| sequence | INTEGER | NOT NULL DEFAULT 10 | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

---

### account.fiscal.position

Table: `account_fiscal_position`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| company_id | INTEGER | FK res_company NOT NULL | |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**account_fiscal_position_tax** (tax mapping):

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| position_id | FK account_fiscal_position NOT NULL | |
| tax_src_id | FK account_tax NOT NULL | tax to replace |
| tax_dest_id | FK account_tax NULL | replacement tax (NULL = remove tax) |

**account_fiscal_position_account** (account mapping):

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| position_id | FK account_fiscal_position NOT NULL | |
| account_src_id | FK account_account NOT NULL | account to replace |
| account_dest_id | FK account_account NOT NULL | replacement account |

---

### account.payment.term

Table: `account_payment_term`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(256) | NOT NULL | |
| note | TEXT | | displayed on invoice |
| early_discount | BOOLEAN | NOT NULL DEFAULT FALSE | |
| discount_percentage | NUMERIC(20,6) | NOT NULL DEFAULT 0 | |
| discount_days | INTEGER | NOT NULL DEFAULT 0 | |
| company_id | INTEGER | FK res_company NOT NULL | |
| active | BOOLEAN | NOT NULL DEFAULT TRUE | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

---

### account.payment.term.line

Table: `account_payment_term_line`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| payment_term_id | INTEGER | FK account_payment_term NOT NULL ON DELETE CASCADE | |
| sequence | INTEGER | NOT NULL DEFAULT 10 | |
| value | VARCHAR(16) | NOT NULL | percent/fixed |
| value_amount | NUMERIC(20,6) | NOT NULL DEFAULT 0 | |
| delay_type | VARCHAR(64) | NOT NULL | days_after / days_after_end_of_month / days_after_end_of_next_month / days_end_of_month_on_the |
| nb_days | INTEGER | NOT NULL DEFAULT 0 | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**Validation**: sum of all lines must equal 100% of invoice total (last line absorbs residual).

---

### account.payment

Table: `account_payment`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| name | VARCHAR(64) | | PAY/YYYY/NNNN |
| payment_type | VARCHAR(16) | NOT NULL | inbound/outbound |
| partner_type | VARCHAR(16) | NOT NULL | customer/supplier |
| partner_id | INTEGER | FK res_partner NOT NULL | |
| journal_id | INTEGER | FK account_journal NOT NULL | bank/cash only |
| currency_id | INTEGER | FK res_currency NOT NULL | |
| amount | NUMERIC(20,6) | NOT NULL | > 0 |
| date | DATE | NOT NULL | |
| ref | VARCHAR(256) | | memo |
| state | VARCHAR(32) | NOT NULL DEFAULT 'draft' | draft/posted/cancelled |
| move_id | INTEGER | FK account_move NULL | the generated journal entry |
| company_id | INTEGER | FK res_company NOT NULL | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**Journal entry on post** (inbound customer):
- Dr 1020 Bank / Cr 1000 Accounts Receivable

**Journal entry on post** (outbound vendor):
- Dr 2000 Accounts Payable / Cr 1020 Bank

---

### account.partial.reconcile

Table: `account_partial_reconcile`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| debit_move_id | INTEGER | FK account_move_line NOT NULL | line with positive balance |
| credit_move_id | INTEGER | FK account_move_line NOT NULL | line with negative balance |
| amount | NUMERIC(20,6) | NOT NULL | matched amount (company currency) |
| debit_amount_currency | NUMERIC(20,6) | NOT NULL DEFAULT 0 | |
| credit_amount_currency | NUMERIC(20,6) | NOT NULL DEFAULT 0 | |
| full_reconcile_id | INTEGER | FK account_full_reconcile NULL | set when fully reconciled |
| company_id | INTEGER | FK res_company NOT NULL | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

**Constraints**:
- Both lines must be on accounts with `reconcile = TRUE`
- Both lines must belong to posted moves
- Both lines must belong to the same `company_id`
- `amount ≤ min(debit_line.amount_residual, abs(credit_line.amount_residual))`

---

### account.full.reconcile

Table: `account_full_reconcile`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | |
| company_id | INTEGER | FK res_company NOT NULL | |
| create_date | TIMESTAMP | DEFAULT now() | |
| write_date | TIMESTAMP | DEFAULT now() | |

Created when a group of partial reconciles brings the combined residual to zero. All participating `account_move_line` rows get `full_reconcile_id` set and `reconciled = TRUE`.

---

## Entity Relationship Summary

```
res_currency ←─── res_company ←─── res_partner
                       │
              account_journal ──→ account_account
                       │                │
              account_move ────────────┤
                   │                   │
         account_move_line ────────────┘
              │        │
    account_tax    account_payment_term_line
              │
  account_tax_repartition_line

account_partial_reconcile (debit_line ↔ credit_line)
account_full_reconcile (1:N account_partial_reconcile)
account_payment ──→ account_move
```

---

## State Machine: account.move

```
        create()
           │
        [draft]  ←──────────────────────────────────────────┐
           │                                                  │
    action_post()                                   action_reset_to_draft()
    (balance check,                                 (only if no reconcile)
     sequence assign)                                         │
           │                                                  │
        [posted] ─────────────────────────────────────────────┘
           │
    action_reverse()
    (creates mirror move)
           │
        [cancel]  (the original; mirror is 'posted')
```
