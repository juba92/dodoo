# ADR-039: Tamper-evident hash chain, line-level immutability, and fiscal lock dates/exceptions

**Status**: Accepted
**Date**: 2026-09-13

## Context

`AccountMove.write` already locks a fixed set of header fields on a posted move, but
`AccountMoveLine.write` performs no state check at all — a posted entry's lines can be freely
edited (FR-008). There is no tamper-evident hash chain (FR-007) and no fiscal lock dates at all
(FR-031/032/033), so nothing prevents back-dated edits to closed periods.

## Decision

`account_journal` gains `restrict_mode_hash_table` (Boolean, default `False`, per-journal
opt-in). `account_move` gains `inalterable_hash` (Char) and `secure_sequence_number` (Integer,
nullable). When `action_post` posts a move whose journal has hash mode on, it computes
`sha256(previous_hash + "|" + name + "|" + date + "|" + amount_total + "|" + sorted_line_tuples)`
and stores it plus the next `secure_sequence_number` (reusing the `account_sequence` table with
prefix `f"HASH/{journal.code}"`). `AccountMove.verify_hash_chain` recomputes every secured move's
hash in order and returns the first mismatch. `AccountMoveLine.write` gains a state check
rejecting writes when the parent move is `posted`/`cancel`. `AccountMove.action_reset_to_draft`
gains two more rejection conditions: `inalterable_hash is not None`, and the move's `date` on/
before the applicable lock date. Lock dates live as four new `res_company` columns
(`fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`, `purchase_lock_date`) added via the
existing `ALTER TABLE` idiom — not a new `account.fiscal.year` model, matching Odoo 19's own
design (lock enforcement reads `res.company` fields directly). A new `AccountLockException` model
(`company_id`, `lock_date_field`, `lock_date`, `user_id`, `journal_id`, `end_date`,
`granted_by_id`, `active`) is checked by `_get_effective_lock_date`. A lock hit does not
hard-fail: `action_post`/`write` push the move's `date` to `lock_date + 1 day` and return a
non-fatal `warning`.

## Rationale

The hash chain reuses `account_sequence`'s existing atomic-upsert table instead of inventing a
second counter. Checking `inalterable_hash`/lock dates inside `action_reset_to_draft` keeps the
single existing "can this move leave posted" choke point intact. Lock dates as plain
`res_company` columns match the reference implementation's own design.

## Alternatives Rejected

A generic "immutable record" mixin — rejected as speculative infrastructure for one model.
Storing the hash chain's previous hash as a live `MAX(...)` query instead of also storing
`secure_sequence_number` — rejected; storing it keeps `verify_hash_chain` an index scan.

## Consequences / Threat Note

Closes A08 (tamper detection) and A01 (only "Accounting Manager" can toggle hash mode or grant a
lock exception, enforced by `require_groups`). Lock-exception grants are audited via
`granted_by_id` (SEC-003).
