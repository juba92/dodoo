# ADR-037: Chart-of-accounts group auto-classification and reconcile-type constraints

**Status**: Accepted
**Date**: 2026-09-13

## Context

`AccountAccount.create`/`write` already forces `reconcile=True` for receivable/payable accounts,
but accounts were never linked to their `account.account.group`, and nothing prevented an
off-balance or cash/credit-card account from being marked reconcilable — both gaps the
008-accounting-parity audit found against Odoo 19 Community (FR-001/FR-002).

## Decision

`AccountAccount.create`/`write` gains two more steps: (1) resolve `group_id` by finding the
`account.account.group` whose `code_prefix_start <= code <= code_prefix_end` (numeric-string
comparison on the account's `code`, matching Odoo's own `_compute_account_group`) and store it —
a plain stored `Many2one`, recomputed on every `create`/`write` that touches `code`, not a live
SQL join at read time; (2) reject `reconcile=True` when `account_type == "off_balance"`, and force
`reconcile=False` (not just "allow false") for `asset_cash`/`liability_credit_card`/`off_balance`
types, mirroring the existing AR/AP-forces-`True` block with a symmetric forces-`False` block for
these three types.

## Rationale

`AccountAccount` already proves the "override `create`/`write`, re-derive a field, call
`super()`" pattern for `reconcile`; extending the same two methods for `group_id` and the
off-balance/cash constraint needs no new mechanism. Storing `group_id` (rather than computing it
at every report query) means `account_report.py`'s existing `GROUP BY a.id, a.code, ...` queries
can add `a.group_id`/`JOIN account_account_group` with no new per-row computation cost.

## Alternatives Rejected

A live SQL `CASE`/join computing the group at report time — rejected because every one of the
five report classes would need the same prefix-range logic duplicated; storing it once at write
time is the existing codebase's approach to derived fields (e.g. `payment_state` is stored, not
computed live, in `account_move.py`).

## Consequences / Threat Note

Low risk: additive field, no behavior change to existing accounts beyond backfilling `group_id`
and closing an open reconcile misconfiguration. No new attack surface.
