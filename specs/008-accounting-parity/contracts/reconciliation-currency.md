# Contract: Reconciliation Write-offs/Suggestions, Multi-Currency (US2)

Covers FR-020…FR-026 (ADR-042).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `res.currency.rate` | `create` / `write` / `read` / `search_read` | `{currency_id, rate_date, rate}` | id / rows | new model, generic CRUD; manual entry only (spec Clarifications — no external provider) |
| `res.company` | `write` | `{income_currency_exchange_account_id, expense_currency_exchange_account_id}` | `True` | new columns (ALTER TABLE), configure once per company |

## REST routes

### `POST /account/reconcile` (changed — was implicit inside `register_against_invoices`; now also directly callable)

Body: `ReconcileWithWriteOff {debit_line_id: int, credit_line_id: int, amount: Decimal | None,
writeoff_account_id: int | None, writeoff_journal_id: int | None}`. When `amount` leaves a residual and
`writeoff_account_id` is supplied, posts a balancing move to that account and fully reconciles both
original lines. Returns `{partial_id: int, full_reconcile_id: int | None, writeoff_move_id: int | None}`.

### `GET /account/payment/{payment_id}/suggestions`

Read-only. Returns up to 10 candidate open invoice/bill lines for the payment's partner, ranked by
amount-closeness then reference similarity: `{"suggestions": [{"move_line_id": int, "move_name": str,
"amount_residual": str, "score": float}]}`. Advisory only — `POST /account/payment/{id}/register`'s
existing required `invoice_ids` body is unchanged.

### `POST /account/currency/revalue`

Body: `{company_id: int, as_of: date}`. Requires `"Accounting Manager"`. For every open
foreign-currency AR/AP line, posts one adjustment move to the exchange accounts and creates its
next-day reversal in `draft` (FR-026). Returns `{result: {entries: [{move_id, reversal_move_id,
amount}]}}`.

## Behavior notes (existing endpoints change internally)

- `POST /account/payment/{payment_id}/register` (existing): now populates
  `debit_amount_currency`/`credit_amount_currency` on the resulting `account.partial.reconcile`, and
  decides full-vs-partial by transaction-currency zero-check when both lines share a foreign currency
  (FR-022). When the two lines' company-currency residuals don't net to zero purely from amount
  matching (because they were booked at different rates), a realized exchange gain/loss line is posted
  automatically to `res_company.income_currency_exchange_account_id`/
  `expense_currency_exchange_account_id` (FR-025) — this appears as an extra entry in the response's
  `reconciled` list, tagged `"kind": "fx_gain_loss"`.
- `POST /account/move/{move_id}/post` (existing): for a move whose `currency_id` differs from the
  company's currency, `amount_currency` on each line is converted into `debit`/`credit` using
  `res.currency.rate`'s rate as of the move's `date` (FR-024) — previously `amount_currency` was stored
  but had no effect on `debit`/`credit` at all.

## Validation models (`account/validators.py`)

```text
class ReconcileWithWriteOff(Payload):
    debit_line_id: int
    credit_line_id: int
    amount: Decimal | None = None
    writeoff_account_id: int | None = None
    writeoff_journal_id: int | None = None

class CurrencyRateCreate(Payload):
    currency_id: int
    rate_date: date
    rate: Decimal = Field(gt=0)

class RunRevaluation(Payload):
    company_id: int
    as_of: date
```
