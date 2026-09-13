# Contract: Payment Term Validation, Due-Date Fix, Early-Payment Discount (US1)

Covers FR-017…FR-019 (ADR-041).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `account.payment.term.line` | `create` / `write` | `{payment_term_id, sequence, value, value_amount, delay_type, nb_days, next_month?: bool}` | id / `True` | `create`/`write` re-sum the parent term's percent-type lines (including this one) and raise `DodooError` if the total ≠ 100 exactly (FR-017). `next_month` (new field) only affects `delay_type="days_end_of_month_on_the"`. |
| `account.payment.term` | `write` | `{early_discount: bool, discount_percentage: float, discount_days: int, early_payment_discount_account_id: int}` | `True` | fields already existed except `early_payment_discount_account_id` (new); this feature is the first thing that reads any of them |

## REST routes

No new dedicated routes — `compute_installments` (already called internally by invoice creation and
by the aged-report/due-date display paths) changes its **return shape**:

```text
# Before (existing keys, unchanged):
[{"due_date": date, "amount": Decimal}, ...]

# After (two new keys, present only when the term's early_discount is True):
[{"due_date": date, "amount": Decimal,
  "discount_date": date | None, "discount_amount": Decimal | None}, ...]
```

`POST /account/payment/{payment_id}/register` (existing route): when the payment's `date` is on or
before an installment's `discount_date`, the reconciled amount is reduced by the discount and the
difference is posted to `early_payment_discount_account_id` — this changes the *amounts* reconciled,
not the request/response shape (still `{invoice_ids: [...]}` → `{reconciled: [...]}`).

## Behavior notes

- The `days_end_of_month_on_the` due-date bug fix (FR-019) is purely internal to `_compute_due_date`;
  no request/response shape changes — only the computed `due_date` value changes for terms that set
  `next_month=True` (terms that never set it keep today's exact output, so no regression for existing
  data).

## Validation models (`account/validators.py`)

```text
class PaymentTermLineCreate(Payload):
    payment_term_id: int
    sequence: int = 10
    value: Literal["percent", "fixed"]
    value_amount: Decimal
    delay_type: Literal["days_after", "days_after_end_of_month",
                         "days_after_end_of_next_month", "days_end_of_month_on_the"]
    nb_days: int = 0
    next_month: bool = False
```
