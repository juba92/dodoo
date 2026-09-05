# ADR-023: Currency-conflict guard keyed on posted account.move.line count

**Status**: Accepted | **Date**: 2026-09-05

## Context

Changing the company country can change the functional currency. Existing posted accounting entries
must not be silently re-based, but a draft-only ledger should switch freely.

## Decision

Before `apply_country_localization` writes anything, if the pack currency differs from the company
currency it counts `account_move_line` joined to `account_move` with `state = 'posted'`. If `> 0`
and the caller did not pass `confirm_currency_change=True`, it returns
`{"applied": False, "warning": "currency_change_requires_confirmation", "from", "to",
"posted_lines"}` and performs no writes (not even `country_id`). With confirmation, or zero posted
lines, it proceeds.

## Consequences

- Implements FR-028 / FR-029 with a precise, testable trigger that matches the accounting module's
  own posted-state gate.
- The declined path has zero side effects; the SPA re-calls with `confirm_currency_change: true`.
- Rejected: blocking on any `account.move` existence (too broad); applying then warning after
  (violates "does not proceed without confirmation").
