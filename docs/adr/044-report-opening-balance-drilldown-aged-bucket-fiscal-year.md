# ADR-044: Financial-report opening balances, drill-down references, aged "not due" bucket, and Balance Sheet earnings split

**Status**: Accepted
**Date**: 2026-09-13

## Context

Trial Balance and General Ledger dropped all activity before a `date_from` filter instead of
showing an opening balance (FR-034). No report exposed `account_id`/`move_id` for drill-down
(FR-035). The aged reports clamped not-yet-due balances into the first overdue bucket instead of
a separate "current" column (FR-036). The Balance Sheet's current-year-earnings figure summed
*all-time* P&L instead of only the current fiscal year (FR-037).

## Decision

`AccountReportTrialBalance`/`AccountReportGeneralLedger` each gain a second, pre-`date_from`
aggregate query merged into each account's row as `opening_balance`; the General Ledger's
window-function running balance starts from that value. All five report classes add `account_id`
(and a representative `move_id` where applicable) to their JSON payloads; the SPA's
`report-view.js` gains a click-through to the journal-entries list. `_BUCKETS` grows from four to
five, prepending `"current"` for `days_overdue <= 0`. `AccountReportBalanceSheet`'s
current-year-earnings calculation is scoped to the fiscal year containing `as_of` (via new
`res_company.fiscalyear_last_month`/`fiscalyear_last_day` columns), and a new
`AccountMove.close_fiscal_year` action posts the prior year's result into the `equity_unaffected`
("Retained Earnings") account.

## Rationale

Every report change is additive to an existing query rather than a rewrite — the two-query
opening-balance approach keeps the already-correct in-period logic untouched. `_BUCKETS`'s
existing generic iteration means extending it from four to five values needs no per-bucket
special-casing anywhere.

## Alternatives Rejected

A `UNION ALL` single-query opening-balance approach — rejected as a more error-prone rewrite of
the General Ledger's window-function query. A full period-close/lock-everything subsystem —
rejected as disproportionate; `close_fiscal_year` is one narrowly-scoped action.

## Consequences / Threat Note

Report figures change (correctly) for any period-filtered query on data with prior-period
activity — this is the intended fix, not a regression, for accounts with no prior-period activity
the opening balance is simply zero.
