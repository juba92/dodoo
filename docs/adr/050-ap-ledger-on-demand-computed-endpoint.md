# ADR-050: AP ledger as an on-demand computed endpoint, reusing `get_ar_ledger`'s pure `_status_and_balance` helper unmodified

**Status**: Accepted
**Date**: 2026-09-20

## Context

User Story 3 (P1) requires showing a vendor's outstanding Accounts Payable balance and posted
bill/credit-note/payment history from the vendor's own record, mirroring 009-customer-database's
AR-ledger requirement (US3) on the receivable side.

## Decision

A new module-level function, `get_ap_ledger(env, partner_id)`, placed in the same
`dodoo/addons/account/models/account_partner.py` file as `get_ar_ledger`. It queries
`account_move`/`account_move_line` for the partner's posted bills/credit notes (`move_type` in the
existing `_PURCHASE_TYPES`) whose lines hit a `liability_payable`-type account, plus
`account_payment` rows with `partner_type = 'supplier'` for the same partner, unions them into one
chronological list of plain dicts in the exact shape `get_ar_ledger` already builds, then hands
that list to the **existing, unmodified** `_status_and_balance(lines)` function. Exposed via
`GET /account/partner/{partner_id}/ap-ledger`. Not a stored/maintained field or table; computed at
read time on every call, in the partner's `property_currency_id` (or company currency if unset).

## Rationale

This is the exact "compute a summary on demand from source rows" convention `get_ar_ledger` already
established for the AR side of the identical problem, and `AccountReportAgedPayable._aged_report`
already proves the same computation works against real posted vendor-bill data specifically.
Reusing `_status_and_balance` verbatim avoids a near-duplicate `_ap_status_and_balance` that could
drift from the AR version over time — the entire reason 009's ADR-047 split that function out as
pure, DB-free logic was to make it reusable independent of which query produced its input.

## Alternatives Rejected

A stored, triggered `res_partner.ap_balance` column — rejected per the resolved spec Clarification,
for the identical reasoning 009's ADR-047 already gives for the AR side. A copy-pasted
`_ap_status_and_balance` — rejected as needless duplication of already-correct, already-unit-tested
arithmetic.

## Consequences / Threat Note

No write path is added to bill/payment posting (`action_post`), so PERF-003 (no regression on
posting) holds structurally, not just by benchmark. The AP-ledger query and the AR-ledger query
share one code path for balance/status classification, so any future bugfix to that logic
automatically benefits both ledgers.
