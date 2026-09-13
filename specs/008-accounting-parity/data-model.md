# Data Model: Accounting Parity with Odoo 19 Community

All fields use `dodoo.core.fields` types (`Char`, `Integer`, `Boolean`, `Float`, `Date`, `Datetime`,
`Text`, `Many2one`, `One2many`, `Many2many`, `Selection`, `Monetary`, `Json`). New tables are created
by `MigrationRunner.install` (`CREATE TABLE IF NOT EXISTS`); new columns on existing tables are added
by the same runner (`ADD COLUMN IF NOT EXISTS`) **except** where a column is added to a table owned by
an addon that must not gain a reverse dependency (`res_company`) — those use the existing
`account_data.py`-style raw `ALTER TABLE` idiom instead of a declared `Field`, exactly like `account`
already does for `res_partner`.

## Changed entities (existing tables)

### `account.account` (table `account_account`)

| Field | Type | Notes |
|---|---|---|
| `group_id` | `Many2one("account.account.group")`, nullable | **NEW.** Resolved automatically in `create`/`write` by matching `code` against `account.account.group.code_prefix_start/end` (numeric-string range comparison); never set directly by a caller. |

**New constraint**: `create`/`write` reject `reconcile=True` when `account_type == "off_balance"`, and
force `reconcile=False` (previously only forced `True` for AR/AP) for `account_type` in
`{"off_balance", "asset_cash", "liability_credit_card"}`.

### `account.account.group` (table `account_account_group`) — unchanged

Already exists (`name`, `code_prefix_start`, `code_prefix_end`, `parent_id`, `company_id`); this
feature is its first consumer via `account.account.group_id`.

### `account.journal` (table `account_journal`)

| Field | Type | Notes |
|---|---|---|
| `restrict_mode_hash_table` | `Boolean`, default `False` | **NEW.** Per-journal opt-in for the hash chain. |

### `account.move` (table `account_move`)

| Field | Type | Notes |
|---|---|---|
| `inalterable_hash` | `Char(size=64)`, nullable | **NEW.** SHA-256 hex digest, set only when posted in a hash-chain journal. |
| `secure_sequence_number` | `Integer`, nullable | **NEW.** Per-journal monotonic counter, set alongside `inalterable_hash`. |
| `debit_origin_id` | `Many2one("account.move")`, nullable | **NEW.** Mirrors `reversed_entry_id`; set on a debit note pointing at the bill/invoice it corrects. |
| `down_payment_origin_id` | `Many2one("account.move")`, nullable | **NEW.** Set on a down-payment move, pointing at the final invoice it will be deducted from. |
| `invoice_cash_rounding_id` | `Many2one("account.cash.rounding")`, nullable | **NEW.** Optional per-move cash-rounding profile. |

**Existing fields reused, not changed**: `state` (`STATE_CHOICES` already includes `cancel`),
`reversed_entry_id`, `posted_before`, `currency_id`, `amount_residual`.

**New/changed behavior** (methods, not columns — see plan.md ADR-038/039/040/042/043/044):
- `action_cancel(env, ids)` — **NEW**, `draft → cancel` only.
- `action_post` — sequence prefix now `journal.code`; idempotent re-post reuses `name` when
  `posted_before=True` and no later move in the journal has a lower number; converts foreign-currency
  `amount_currency` to `debit`/`credit` via `res.currency.rate`; applies `invoice_cash_rounding_id`;
  computes `inalterable_hash`/`secure_sequence_number` when the journal has hash mode on; rejects
  posting at/before an effective lock date (see `account.lock.exception` below), auto-advancing the
  move's `date` and returning a non-fatal warning instead of hard-failing.
- `action_reverse(..., auto_post: bool = True)` — **changed signature**; when `False`, leaves the
  reversal in `draft`.
- `action_reset_to_draft` — gains two more rejection conditions: `inalterable_hash is not None`, and
  `date` on/before the effective lock date.
- `action_create_debit_note(env, move_id, uid)` — **NEW**; copies lines verbatim (no sign flip), sets
  `debit_origin_id`.
- `apply_down_payments(env, invoice_id)` — **NEW**; called from `action_post` for invoice-type moves.
- `revalue_currency_balances(env, company_id, as_of, uid)` — **NEW**, stateless; posts one adjustment
  move per open foreign-currency AR/AP account plus its draft next-day reversal.
- `close_fiscal_year(env, company_id, fiscal_year_end, uid)` — **NEW**, narrowly scoped; posts one
  entry moving the prior year's P&L result into the `equity_unaffected` account.
- `verify_hash_chain(env, journal_id)` — **NEW**, read-only; recomputes and compares.

### `account.move.line` (table `account_move_line`)

| Field | Type | Notes |
|---|---|---|
| `discount` | `Monetary`, default `0` | **NEW.** Percentage 0–100. |
| `display_type` | `Selection`, existing | Gains one new value: `"down_payment"` (alongside `product`/`tax`/`payment_term`/`line_section`/`line_note`). |

**New constraint on `write`**: rejects any change when the parent move's `state` is `posted` or
`cancel` (mirrors `AccountMove.write`'s existing header guard; here it applies to every field, not a
subset — no line field has a legitimate post-posting external-write case). **New constraint on
`create`/`write`**: when `analytic_distribution` (already-existing `Json`, previously unvalidated) is
set, every key must resolve to an active `analytic.account` id and the values must sum to `100` (±0.01).

### `account.payment.term.line` (table `account_payment_term_line`)

| Field | Type | Notes |
|---|---|---|
| `next_month` | `Boolean`, default `False` | **NEW.** Companion to `nb_days` for `delay_type="days_end_of_month_on_the"` — targets the *next* month's `nb_days`-th day when `True`, the invoice date's own month otherwise (today's behavior, unchanged when this flag is left `False`). |

**New constraint on `create`/`write`**: for `value == "percent"` lines, the parent term's percent-type
lines (including the one being written) must sum to exactly 100 — enforced eagerly, not deferred.

### `account.payment.term` (table `account_payment_term`)

| Field | Type | Notes |
|---|---|---|
| `early_payment_discount_account_id` | `Many2one("account.account")`, nullable | **NEW.** Where the discount taken (the gap between the installment's face amount and its discounted amount) is posted when a payment lands on or before `discount_date`. Required only when `early_discount` is `True` — enforced at write time, not a DB `NOT NULL` (matching the codebase's existing conditional-requirement style, e.g. `account.cash.rounding.account_id`). |

`compute_installments`'s return shape gains two new keys per installment (not a schema change — it's
already a computed dict, not a stored row): `discount_date` (`invoice_date + discount_days` when
`early_discount` is `True`), `discount_amount` (the installment amount less `discount_percentage`).

### `account.partial.reconcile` (table `account_partial_reconcile`) — no new columns

`debit_amount_currency`/`credit_amount_currency` (already-declared, previously unused) are now
populated and read. `reconcile_lines` gains two new optional parameters (not columns):
`writeoff_account_id`, `writeoff_journal_id`.

### `account.tax.repartition.line` (table `account_tax_repartition_line`)

| Field | Type | Notes |
|---|---|---|
| `tag_ids` | `Many2many("account.account.tag", relation_table="account_tax_repartition_line_tag_rel", column1="repartition_line_id", column2="tag_id")` | **NEW.** The tax-grid assignment. |

### `res.company` (table `res_company`, owned by `base`)

Columns added by `account`'s own `account_data.py` via the existing raw-`ALTER TABLE` idiom (not a
declared `Field` in `base`'s `ResCompany` class — same reasoning as the existing `property_account_*`
columns `account` already adds to `res_partner`):

| Column | Type | Notes |
|---|---|---|
| `fiscalyear_lock_date` | `DATE`, nullable | All-journals hard lock. |
| `tax_lock_date` | `DATE`, nullable | Tax-return lock. |
| `sale_lock_date` | `DATE`, nullable | Sales-journal lock. |
| `purchase_lock_date` | `DATE`, nullable | Purchase-journal lock. |
| `income_currency_exchange_account_id` | `INTEGER` → `account_account.id` | Realized/unrealized FX gain account. |
| `expense_currency_exchange_account_id` | `INTEGER` → `account_account.id` | Realized/unrealized FX loss account. |
| `fiscalyear_last_month` | `INTEGER`, default `12` | Fiscal-year-end month, for Balance Sheet current-year-earnings scoping. |
| `fiscalyear_last_day` | `INTEGER`, default `31` | Fiscal-year-end day. |

`tax_rounding_method` — **already exists**, no change to `base`; only `account`'s own tax-computation
code starts reading it.

### `res.currency` (table `res_currency`, `base`) — no new columns on this table itself

Gains a new sibling model, `res.currency.rate` (below), in the same file.

## New entities

### `res.currency.rate` (table `res_currency_rate`) — new, in `base`

| Field | Type | Notes |
|---|---|---|
| `currency_id` | `Many2one("res.currency")`, required | |
| `rate_date` | `Date`, required | |
| `rate` | `Monetary`, required | Company-currency units per 1 unit of `currency_id` (Odoo's convention). |

Uniqueness: at most one rate per `(currency_id, rate_date)` (enforced at the write boundary, not a DB
unique constraint, matching the codebase's existing validate-then-write style). Consumed via
`ResCurrencyRate.get_rate(env, currency_id, company_currency_id, date)` — looks up the latest
`rate_date <= date`.

### `account.lock.exception` (table `account_lock_exception`) — new, in `account`

| Field | Type | Notes |
|---|---|---|
| `company_id` | `Many2one("res.company")`, required | |
| `lock_date_field` | `Selection([("fiscalyear_lock_date", …), ("tax_lock_date", …), ("sale_lock_date", …), ("purchase_lock_date", …)])`, required | Which company lock this exception relaxes. |
| `lock_date` | `Date`, required | The exception's own (later, more permissive) date — a move dated after this is still blocked. |
| `user_id` | `Many2one("res.users")`, nullable | `NULL` = applies to any user. |
| `journal_id` | `Many2one("account.journal")`, nullable | `NULL` = applies to any journal. |
| `end_date` | `Date`, required | Exception expires after this date. |
| `granted_by_id` | `Many2one("res.users")`, required | Set automatically to the acting user (Accounting Manager) at creation — SEC-003 audit trail. |
| `active` | `Boolean`, default `True` | |

Consulted via `_get_effective_lock_date(env, company_id, field, user_id, journal_id, today)`.

### `account.bank.statement` (table `account_bank_statement`) — new, in `account`

| Field | Type | Notes |
|---|---|---|
| `journal_id` | `Many2one("account.journal")`, required | Must be a `bank`/`cash`-type journal. |
| `date` | `Date`, required | |
| `balance_start` | `Monetary`, required | |
| `balance_end_real` | `Monetary`, required | Bank-reported ending balance. |
| `state` | `Selection([("open", …), ("confirmed", …)])`, default `"open"` | |
| `company_id` | `Many2one("res.company")`, required | |

**Continuity rule** (FR-028): confirming a statement (`open → confirmed`) checks the immediately-prior
statement on the same `journal_id` (by `date`) has `balance_end_real == this.balance_start`; a
read-time `get_status` also flags `is_complete = (balance_start + SUM(lines.amount) == balance_end_real)`.

### `account.bank.statement.line` (table `account_bank_statement_line`) — new, in `account`

| Field | Type | Notes |
|---|---|---|
| `statement_id` | `Many2one("account.bank.statement")`, required | |
| `date` | `Date`, required | |
| `payment_ref` | `Char(size=256)`, nullable | Bank-reported description/reference. |
| `partner_id` | `Many2one("res.partner")`, nullable | |
| `amount` | `Monetary`, required | Signed (positive = inbound). |
| `move_line_id` | `Many2one("account.move.line")`, nullable | Set once reconciled via `reconcile_against`. |

### `account.cash.rounding` (table `account_cash_rounding`) — new, in `account`

| Field | Type | Notes |
|---|---|---|
| `name` | `Char(size=128)`, required | |
| `rounding` | `Monetary`, required | The rounding increment (e.g. `0.05`). |
| `rounding_method` | `Selection([("up", …), ("down", …), ("half_up", …)])`, required | |
| `strategy` | `Selection([("add_invoice_line", …), ("biggest_tax", …)])`, required | |
| `account_id` | `Many2one("account.account")`, nullable | Required when `strategy == "add_invoice_line"`. |
| `company_id` | `Many2one("res.company")`, required | |

### `account.account.tag` (table `account_account_tag`) — new, in `account`

| Field | Type | Notes |
|---|---|---|
| `name` | `Char(size=128)`, required | The grid label (e.g. "Base Sales", "Tax Due"). |
| `applicability` | `Selection([("taxes", …)])`, default `"taxes"` | Only tax-repartition tagging is in scope for this feature. |
| `country_id` | `Many2one("res.country")`, nullable | For localization-specific grids. |

### `analytic.plan` (table `analytic_plan`) — new addon `dodoo/addons/analytic/`

| Field | Type | Notes |
|---|---|---|
| `name` | `Char(size=128)`, required | |
| `parent_id` | `Many2one("analytic.plan")`, nullable | Simple hierarchy — no applicability-rule engine. |
| `company_id` | `Many2one("res.company")`, required | |

### `analytic.account` (table `analytic_account`) — new addon `dodoo/addons/analytic/`

| Field | Type | Notes |
|---|---|---|
| `name` | `Char(size=128)`, required | |
| `code` | `Char(size=32)`, nullable | |
| `plan_id` | `Many2one("analytic.plan")`, nullable | |
| `company_id` | `Many2one("res.company")`, required | |
| `active` | `Boolean`, default `True` | |

No `analytic.line` model — `account.move.line.analytic_distribution` (existing JSON,
`{analytic_account_id: percentage}`) is the roll-up source, queried directly by
`AccountReportAnalytic`, per ADR-045/D6.

## Reports (virtual — no new tables; existing `_VirtualReport` pattern)

- `AccountReportTax` (new) — sums posted invoice/bill tax and base amounts grouped by
  `account.account.tag` for a period.
- `AccountReportAnalytic` (new) — sums posted `account_move_line.balance × analytic_distribution[key]`
  grouped by `analytic_account_id` for a period.
- `AccountReportTrialBalance`, `AccountReportGeneralLedger` (existing, extended) — each row gains
  `account_id` (already selected internally; now also returned) and an `opening_balance` value per
  account, computed from posted lines dated before `date_from`.
- `AccountReportBalanceSheet` (existing, extended) — `current_year_earnings` now scoped to the fiscal
  year containing `as_of` (via `fiscalyear_last_month`/`fiscalyear_last_day`), not all-time.
- `AccountReportAgedReceivable`/`AccountReportAgedPayable` (existing, extended) — bucket set grows from
  four (`b_0_30`, `b_31_60`, `b_61_90`, `b_90_plus`) to five, prepending `current` for `days_overdue <= 0`.

## State transitions

```
account.move.state:
  draft ──action_post──▶ posted ──action_reverse(auto_post=True)──▶ posted (new reversal move)
    │                       │
    │                       ├──action_reverse(auto_post=False)──▶ draft (new reversal move, unposted)
    │                       │
    │                       └──action_reset_to_draft──▶ draft
    │                            (blocked if: reconciled lines, inalterable_hash set, or
    │                             date on/before effective lock date without an exception)
    │
    └──action_cancel──▶ cancel   (NEW — draft only; a posted move must be reversed, never cancelled)

account.bank.statement.state:
  open ──action_confirm──▶ confirmed
    (blocked if: continuity check against the prior statement fails)

account.lock.exception:
  created (active=true) ──(end_date passes)──▶ inert (still active=true in storage, but
                                                        _get_effective_lock_date ignores it —
                                                        no separate "expired" state needed)
```
