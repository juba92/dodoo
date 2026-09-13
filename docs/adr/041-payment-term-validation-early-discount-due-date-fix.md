# ADR-041: Payment-term validation, early-payment-discount activation, and due-date fix

**Status**: Accepted
**Date**: 2026-09-13

## Context

Nothing validated that a payment term's percent-type lines summed to 100% (FR-017). The
`early_discount`/`discount_percentage`/`discount_days` fields existed on `AccountPaymentTerm` but
were never read anywhere (FR-018). The `days_end_of_month_on_the` delay type always clamped
within the invoice date's own month, never a configurable next month (FR-019).

## Decision

`AccountPaymentTermLine` gains a `create`/`write` override that re-sums the parent term's
percent-type lines (including the one being written) and raises `DodooError` if the total ≠ 100.
`_compute_due_date`'s `days_end_of_month_on_the` branch is fixed to resolve the target month
first (current, or next when a new `next_month` Boolean field is `True`) and then clamp the
configured day within that resolved month's length.
`AccountPaymentTerm.compute_installments` is extended to also return, per installment,
`discount_date` (`invoice_date + discount_days`) and `discount_amount` (the installment amount
reduced by `discount_percentage`) when `early_discount` is `True`. A new
`early_payment_discount_account_id` field says where the discount taken is posted.

## Rationale

`compute_installments` is already the single function every caller goes through, so adding the
two discount keys here makes them available everywhere with no second lookup path. The 100%-sum
constraint at write time (not post time) matches how `AccountAccount`'s reconcile constraint is
already enforced at write time in this codebase.

## Alternatives Rejected

Validating the 100% sum only when the term is used on an invoice — rejected; it would let an
already-broken term sit in the chart of payment terms indefinitely.

## Consequences / Threat Note

Low risk: an existing term with lines that already summed to 100% is unaffected; only genuinely
invalid terms are now rejected at save time instead of silently mis-computing later.
