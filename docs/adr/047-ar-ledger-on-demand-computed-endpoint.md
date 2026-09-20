# ADR-047: AR ledger as an on-demand computed endpoint, not a stored entity

**Status**: Accepted
**Date**: 2026-09-20

## Context

Customer Database's User Story 3 (P1) requires showing a customer's outstanding Accounts
Receivable balance plus the invoice/credit-note/payment history behind it, kept current as
documents post and reconcile (spec.md Clarifications, 2026-09-20).

## Decision

A new module-level function, `get_ar_ledger(env, partner_id)` — **not** a method on `base`'s
`ResPartner` class, since `res.partner` lives in `base` but this query is an accounting concern —
lives in a new `dodoo/addons/account/models/account_partner.py`. It queries `account_move`/
`account_move_line` for the partner's posted invoices/credit notes (`move_type` in the existing
`_SALE_TYPES`) whose lines hit an `asset_receivable`-type account, plus `account_payment` rows,
unions them into one chronological list of plain dicts, then hands that list to a second, pure
function, `_status_and_balance(lines)` (no DB access), which returns the final
`(balance, lines_with_status)`. Exposed via `GET /account/partner/{partner_id}/ar-ledger`. Not a
stored/maintained field or table; computed at read time on every call.

## Rationale

This is the exact "compute a summary on demand from source rows" convention
`AccountAccount.get_balance` already established, and the read-time `is_complete` check
`AccountBankStatement.get_status` uses. Using `amount_residual` (already populated by every
existing posting/reconciliation path) instead of re-deriving payment status from scratch means the
AR ledger's status can never drift from what reconciliation has already computed. Splitting out
`_status_and_balance` as a pure function makes the balance/status computation unit-testable
without Postgres (Principle II) — the same "pure-logic piece with no DB" shape
008-accounting-parity's own unit tests already use for tax/due-date math.

## Alternatives Rejected

A stored, triggered `res_partner.ar_balance` column recomputed on every invoice/payment/
reconciliation write — rejected per the resolved spec Clarification (avoids a second write path
across four different posting flows that could drift). A general-purpose "partner ledger" report
class reusable for both AR and AP in one call — rejected as premature generalization; this feature
only needs the customer (AR) side.

## Consequences / Threat Note

The endpoint is read-only and session-authenticated like every other report endpoint in this
addon; the query uses parameterized SQLAlchemy `text()` only, never string-interpolated
`partner_id`. No write path is added to the invoice/payment posting flow (PERF-003).

**Performance iteration** (PERF-002, measured via `EXPLAIN ANALYZE` against a live 5,000-line
benchmark on a 100k-row `account_move`/`account_move_line` table — not guessed upfront):
1. No index on `account_move.partner_id` at all (none existed before this feature): 13.7s.
2. Added `idx_account_move_partner_type (partner_id, move_type)`: the outer `account_move` filter
   became fast, but the subsequent join to `account_move_line`'s `payment_term` line got *worse*
   (20.5s) — the planner mis-estimated a plain `(move_id, display_type)` composite index as
   low-selectivity and fell back to scanning `idx_account_move_line_display_type` (~1/6 of the
   whole table) once per outer row instead.
3. Replaced that composite index with a **partial** index scoped to exactly this query's predicate,
   `idx_account_move_line_payment_term_move (move_id) WHERE display_type = 'payment_term'` — this
   gives the planner unambiguous selectivity information. Result: 19ms.

Both indexes are now in `account/data/indexes.py`'s `PERF_INDEXES`. This is a concrete instance of
why this feature's own benchmark tests (not just a plausible-sounding index chosen by inspection)
are what actually verify PERF-002 — the "obvious" index was measurably wrong twice before the
right one was found.
