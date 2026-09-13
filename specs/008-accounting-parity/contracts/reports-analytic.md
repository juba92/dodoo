# Contract: Financial Report Corrections, Tax Report, Analytic Accounting (US4, US6)

Covers FR-034…FR-039 (ADR-044/045).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `analytic.plan` | `create` / `read` / `search_read` | `{name, parent_id?, company_id}` | id / rows | new addon `dodoo/addons/analytic/`, generic CRUD |
| `analytic.account` | `create` / `read` / `search_read` | `{name, code?, plan_id?, company_id, active?}` | id / rows | new addon `dodoo/addons/analytic/`, generic CRUD |
| `account.move.line` | `write` | `{analytic_distribution: {"<analytic_account_id>": <percent>, ...}}` | `True` | every key must resolve to an active `analytic.account`; values must sum to 100 (±0.01), else `DodooError` |

## REST routes (all existing, response shape extended — no new paths)

### `GET /account/report/trial-balance?date_from=&date_to=&company_id=`

Each row gains `account_id` (int) and `opening_balance` (str) — the account's balance from all posted
activity strictly before `date_from` (FR-034). `debit`/`credit`/`balance` keep their existing meaning
(in-period movement only); the caller adds `opening_balance` to get the period-end balance.

### `GET /account/report/general-ledger?account_id=&date_from=&date_to=&company_id=`

Each account section gains `opening_balance` (str); `running_balance` on each line now starts from
that value instead of zero (FR-034). Each line gains `move_id` (int) for drill-down (FR-035).

### `GET /account/report/profit-loss?date_from=&date_to=&company_id=`

Each line gains `account_id`.

### `GET /account/report/balance-sheet?date=&company_id=`

`current_year_earnings` is now scoped to the fiscal year containing `date` (via the company's
`fiscalyear_last_month`/`fiscalyear_last_day`), not all-time (FR-037). Each line gains `account_id`.

### `GET /account/report/aged-receivable?date=&company_id=` / `GET /account/report/aged-payable?...`

The bucket set grows from four to five: `current`, `b_0_30`, `b_31_60`, `b_61_90`, `b_90_plus` —
`current` holds balances not yet due (`days_overdue <= 0`), previously folded into `b_0_30` (FR-036).
Every response object (`partners[]`, `totals`) gains the `current` key alongside the existing four.
Each partner's line-level detail (if included) gains `move_id`.

### `GET /account/report/tax-report?date_from=&date_to=&company_id=` (NEW)

See `invoicing-tax-engine.md` for the full shape.

### `GET /account/report/analytic?date_from=&date_to=&analytic_account_id=&company_id=` (NEW)

Returns amounts rolled up by analytic account for posted lines in range:
`{"lines": [{"analytic_account_id": int, "analytic_account_name": str, "amount": str}],
"total": str}`. `analytic_account_id` is an optional filter; omitted returns all accounts with any
posted activity in range.

### `POST /account/fiscal-year/close`

Body: `{company_id: int, fiscal_year_end: date}`. Requires `"Accounting Manager"`. Posts one entry
moving the closing fiscal year's net P&L result into the `equity_unaffected` account (the seeded
"Retained Earnings" account), making the Balance Sheet's current-vs-prior-year split (FR-037)
meaningful going forward. Returns `{result: {closing_move_id: int}}`.

## Validation models (`account/validators.py` and the new `analytic/validators.py`)

```text
# account/validators.py
class FiscalYearClose(Payload):
    company_id: int
    fiscal_year_end: date

# analytic/validators.py
class AnalyticPlanCreate(Payload):
    name: str
    parent_id: int | None = None
    company_id: int

class AnalyticAccountCreate(Payload):
    name: str
    code: str | None = None
    plan_id: int | None = None
    company_id: int
    active: bool = True
```
