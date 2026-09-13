# Contract: Bank Statements, Cash Rounding, Fiscal Lock Dates/Exceptions (US2)

Covers FR-027…FR-033 (ADR-043).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `account.bank.statement` | `create` / `read` / `search_read` | `{journal_id, date, balance_start, balance_end_real}` | id / rows | `state` defaults `"open"`, generic CRUD |
| `account.bank.statement.line` | `create` (bulk) | `[{statement_id, date, payment_ref, partner_id?, amount}, ...]` | ids | manual/API entry only — no file-format import (spec Clarifications) |
| `account.cash.rounding` | `create` / `read` / `search_read` | `{name, rounding, rounding_method, strategy, account_id?}` | id / rows | generic CRUD |
| `res.company` | `write` | `{fiscalyear_lock_date?, tax_lock_date?, sale_lock_date?, purchase_lock_date?}` | `True` | new columns, ALTER TABLE |

## REST routes

### `POST /account/statement/{statement_id}/confirm`

Body: `{}`. Checks continuity against the prior statement on the same journal (FR-028); `400
DodooError` if `balance_start` doesn't match the prior statement's `balance_end_real`. Transitions
`open → confirmed`. Returns `{result: true}`.

### `GET /account/statement/{statement_id}/status`

Read-only. Returns `{"complete": bool, "computed_balance": str, "declared_balance": str}` (FR-028's
own-statement completeness check, independent of cross-statement continuity).

### `POST /account/statement/{statement_id}/line/{line_id}/reconcile`

Body: `{move_line_ids: [int, ...]}`. Reconciles the statement line against one or more existing posted
`account.move.line` rows summing to its `amount`, via the same engine `reconciliation-currency.md`
describes (a statement line is just another reconciliation counterparty). Sets `move_line_id` on an
exact 1:1 match, or splits into child statement lines for a 1:N match. Returns
`{result: {reconciled: [...]}}` (same shape as `POST /account/reconcile`'s).

### `POST /account/lock-exception`

Body: `LockExceptionGrant`. **Requires `"Accounting Manager"`**. Sets `granted_by_id` to the acting
user automatically (SEC-003). Returns `{result: {lock_exception_id: int}}`.

### `DELETE /account/lock-exception/{id}`

Requires `"Accounting Manager"`. Sets `active=False` (soft-revoke, auditable). Returns
`{result: true}`.

## Behavior notes (existing endpoint changes internally)

- `POST /account/move/{move_id}/post` and the generic `write` on `account.move`: both now call
  `_get_effective_lock_date` before touching a move dated at/before the company's relevant lock date.
  If an active, matching `account.lock.exception` exists (by `user_id`/`journal_id`, unexpired), the
  action proceeds; otherwise the move's `date` is advanced to `lock_date + 1 day` and a `warning` key is
  returned (FR-032) — see `coa-journals-audit-trail.md`'s note on the `post` route.
- Cash rounding: an invoice/bill posted with `invoice_cash_rounding_id` set gets one extra rounding
  line (`add_invoice_line`) or an adjustment to its largest tax line (`biggest_tax`) inserted during
  `action_post`, same as an ordinary tax line — no separate endpoint.

## Validation models (`account/validators.py`)

```text
class BankStatementCreate(Payload):
    journal_id: int
    date: date
    balance_start: Decimal
    balance_end_real: Decimal

class BankStatementLineCreate(Payload):
    statement_id: int
    date: date
    payment_ref: str | None = None
    partner_id: int | None = None
    amount: Decimal

class StatementLineReconcile(Payload):
    move_line_ids: list[int]

class CashRoundingCreate(Payload):
    name: str
    rounding: Decimal = Field(gt=0)
    rounding_method: Literal["up", "down", "half_up"]
    strategy: Literal["add_invoice_line", "biggest_tax"]
    account_id: int | None = None

class LockExceptionGrant(Payload):
    company_id: int
    lock_date_field: Literal["fiscalyear_lock_date", "tax_lock_date",
                              "sale_lock_date", "purchase_lock_date"]
    lock_date: date
    user_id: int | None = None
    journal_id: int | None = None
    end_date: date
```
