# ADR-043: Bank statements, continuity validation, statement-line reconciliation, and cash rounding

**Status**: Accepted
**Date**: 2026-09-13

## Context

There was no bank statement entity at all — payments post directly with nothing to reconcile
against (FR-027/028/029). There was no cash-rounding support for cash-paying customers (FR-030).

## Decision

Two new `account`-owned models: `AccountBankStatement` (`journal_id`, `date`, `balance_start`,
`balance_end_real`, `state`, `company_id`) and `AccountBankStatementLine` (`statement_id`, `date`,
`payment_ref`, `partner_id`, `amount`, `move_line_id`). `action_confirm` (`open → confirmed`)
checks the prior statement on the same journal has a `balance_end_real` equal to this one's
`balance_start`; a read-time `get_status` checks `balance_start + SUM(lines.amount) ==
balance_end_real`. `AccountBankStatementLine.reconcile_against` links a statement line to one or
more posted `account.move.line` rows summing to its amount. `AccountCashRounding` (`rounding`,
`rounding_method`, `strategy`, `account_id`) is applied in `action_post` right after tax
computation, inserting an adjustment line (`add_invoice_line`) or adjusting the largest tax line
(`biggest_tax`).

## Rationale

Placing both new models directly in `account` matches the reference implementation's own
placement — no addon-boundary question, unlike the `stock`/`stock_account` split. Read-time
`is_complete` avoids a second write path that could drift from the lines it summarizes.

## Alternatives Rejected

Parsing specific bank file formats (CSV/OFX/CAMT.053) — explicitly out of scope per the spec's
Clarifications; statement lines are created via the plain CRUD/bulk-create route.

## Consequences / Threat Note

Purely additive — no existing payment/reconciliation behavior changes; a statement is an optional
new checkpoint an accountant can choose to use.
