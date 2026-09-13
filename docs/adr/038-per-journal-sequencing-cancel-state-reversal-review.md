# ADR-038: Per-journal sequencing, cancel-state activation, reused-number-on-repost, and draft-reversal option

**Status**: Accepted
**Date**: 2026-09-13

## Context

`AccountMove.action_post` keyed its sequence by `move_type` (a static `_JOURNAL_PREFIX` dict),
letting two journals of the same type share one number stream (FR-003). `STATE_CHOICES` already
lists `"cancel"` but nothing ever transitions a move into it (FR-004). Resetting a posted,
previously-posted move to draft and re-posting always burns a new sequence number, leaving a gap
(FR-005). `action_reverse` always force-posts the reversal with no review step (FR-006).

## Decision

1. `AccountMove.action_post` and `AccountPayment.action_post` derive the sequence `prefix` from
   the posting journal's own `code` column instead of the static `_JOURNAL_PREFIX[move_type]`
   dict — `account_sequence`'s existing `PRIMARY KEY (prefix, year)` already scopes correctly
   once `prefix` is journal-specific; no DDL change.
2. `action_post` becomes idempotent on `posted_before=True` moves: before calling
   `get_next_sequence`, it checks whether `name` is already set and no other move in the same
   journal has a lower sequence number with a later date; if so it reuses the existing `name`.
3. A new `AccountMove.action_cancel` classmethod transitions `draft → cancel` only (matching
   `STATE_CHOICES`'s existing, currently-unreachable `"cancel"` value).
4. `action_reverse` gains an `auto_post: bool = True` parameter; when `False` the reversal move is
   created and left in `draft` for the caller to review/adjust before posting manually.

## Rationale

Every change edits an existing method's inputs or adds one new classmethod next to its siblings
— no new file, no new table. Deriving the prefix from `journal.code` costs one extra `SELECT`
already inside `action_post`'s existing per-move loop where `journal_id` is already fetched.

## Alternatives Rejected

A new `ir.sequence`-style child model per journal (Odoo's actual mechanism) — rejected as
disproportionate new infrastructure; the existing free-form `prefix` string already equals the
seeded journal codes. A `cancel` action that also cancels already-posted moves — rejected;
Odoo's own `button_cancel` only cancels draft entries, never a posted one (that requires
reversal).

## Consequences / Threat Note

Existing sequences/move names are unaffected since seeded journal codes (`INV`/`BILL`/`CSH`/
`BNK`/`MISC`) are identical to the prior `_JOURNAL_PREFIX` values. No new attack surface.
