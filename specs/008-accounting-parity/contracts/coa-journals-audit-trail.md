# Contract: Chart of Accounts, Journal Sequencing, Cancel, Hash Chain, Immutability (US3)

Covers FR-001…FR-009 (ADR-037/038/039). `account.account`/`account.account.group`/`account.journal`
CRUD stays generic JSON-RPC (`create`/`write`/`read`/`search_read`, no dedicated routes needed); the
new behavior surfaces as three new REST actions plus one changed one, each requiring
`require_groups(env, uid, "Accounting User", "Accounting Manager")` for the state-changing ones and
`"Accounting Manager"` alone for the hash-chain toggle (ADR-037's security-surface introduction).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `account.account` | `create` / `write` | standard, `{code, name, account_type, reconcile?, ...}` | id / `True` | `group_id` is auto-resolved server-side from `code`; never accepted as an input field (silently ignored if sent, per FR-001). `reconcile=True` on `account_type in {off_balance, asset_cash, liability_credit_card}` raises `DodooError` (FR-002). |
| `account.account.group` | `create` / `write` / `read` | standard, `{name, code_prefix_start, code_prefix_end, parent_id?}` | — | unchanged; this feature is `group_id`'s first consumer |
| `account.journal` | `write` | `{restrict_mode_hash_table: bool}` | `True` | flips hash-chain mode; only takes effect for moves posted *after* the flip — never retroactive |

## REST routes

### `POST /account/move/{move_id}/cancel`

Body: `{}`. Requires `state == "draft"` (a posted move must be reversed, never cancelled directly —
FR-004/FR-008 boundary). Transitions `draft → cancel`. `400 DodooError` if not draft. Returns
`{result: true}`.

### `POST /account/move/{move_id}/reverse` (changed)

Body: `ReverseMove {date?: date, journal_id?: int, auto_post: bool = True}`. When `auto_post` is
`False`, the created reversal move is left in `draft` instead of being posted immediately (FR-006).
Returns `{result: [reversal_move_id], state: "draft" | "posted"}` (the `state` key is new, telling the
caller which branch was taken).

### `POST /account/journal/{journal_id}/hash-chain`

Body: `{enabled: bool}`. **Requires `"Accounting Manager"`** (ADR-037). Sets
`restrict_mode_hash_table`. Returns `{result: true}`.

### `GET /account/journal/{journal_id}/verify-hash-chain`

Read-only. Recomputes every secured move's hash in `secure_sequence_number` order for the journal and
returns the first mismatch, if any: `{valid: bool, first_break_move_id: int | None}`.

## Behavior notes (no new endpoint — existing endpoints change internally)

- `POST /account/move/{move_id}/post` (existing route, unchanged signature): the sequence number's
  `prefix` now comes from the posting journal's `code` column instead of a `move_type`-keyed constant
  (FR-003) — **not observable in the response shape**, only in the resulting `name` value. Re-posting a
  `posted_before=True` move (after a reset-to-draft with no date reordering) reuses its original `name`
  instead of allocating a new one (FR-005). When the journal has `restrict_mode_hash_table=True`, the
  response gains `inalterable_hash`/`secure_sequence_number` in the read payload. When the move's `date`
  falls at/before the company's effective lock date (see `bank-cash.md` for the lock-date model) and no
  exception applies, the move's `date` is silently advanced to `lock_date + 1 day` and the response gains
  a `warning: str` key (FR-032) — this is not an error (still `200`).
- Any `PUT`/`write` on `account.move.line` for a line whose parent move is `posted` or `cancel` now
  raises the same `DodooError` shape `account.move.write` already raises for its header fields
  (FR-008) — this is a JSON-RPC-level change (the generic `write` dispatch), not a new REST route.

## Validation models (`account/validators.py`, NEW file)

```text
class ReverseMove(Payload):
    date: date | None = None
    journal_id: int | None = None
    auto_post: bool = True

class HashChainToggle(Payload):
    enabled: bool

class CancelMove(Payload):
    pass  # empty body; kept as a named model for consistency with every other action route
```
