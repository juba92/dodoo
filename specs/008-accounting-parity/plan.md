# Implementation Plan: Accounting Parity with Odoo 19 Community

**Branch**: `008-accounting-parity` | **Date**: 2026-09-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-accounting-parity/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Close the 39 gaps/divergences (FR-001…FR-039) the spec's audit found between `dodoo/addons/account`
and `../odoo-19.0/addons/account`, almost entirely inside the existing `account` addon, plus one small,
same-owner addition to `base` (a new `res.currency.rate` model, exactly where Odoo itself puts it), one
cross-addon `ALTER TABLE` extension of `res_company` (the same idiom `account` already uses on
`res_partner`, and `stock_account` uses on `product_category`), and **one new addon**,
`dodoo/addons/analytic/`, for analytic accounting — confirmed by reading
`../odoo-19.0/addons/account/__manifest__.py` directly (`'depends': [..., 'analytic', ...]`) that Odoo
19 Community itself keeps analytic accounting as a separate module `account` depends on, exactly the
`product`/`stock`/`stock_account` module-boundary precedent 007-inventory already established in this
codebase. Every other gap is a correction or an addition to a model, endpoint, or view `account`
already owns. The work splits into nine coherent design decisions (ADR-037…045 below): chart-of-accounts classification;
per-journal sequencing/cancel-state/reversal-review; the hash-chain + line-immutability + lock-date
audit-trail layer; a rewritten discount/price-included/rounding-method-aware tax engine (plus debit
notes and down payments); payment-term validation and early-discount activation; reconciliation
write-offs/suggestions and the new multi-currency rate/FX-gain-loss engine; bank statements and cash
rounding; financial-report opening-balance and drill-down correctness; and analytic accounting. Every
decision reuses a pattern the codebase already has proof for — the `account`→`res_partner`
`ALTER TABLE` idiom, the `create`/`write` classmethod-override guard pattern from `AccountAccount` and
`AccountMove`, the per-addon `require_groups`/`validators.py` convention from `hr`/`product`, and the
`account_sequence` atomic-upsert table — rather than introducing new core infrastructure.

## Technical Context

**Language/Version**: Python 3.12 (matches 001–007; no change).

**Primary Dependencies**: FastAPI (`dodoo.http.routing.route`), SQLAlchemy Core async + asyncpg
(`dodoo.core.models.BaseModel` / `dodoo.core.fields`), Pydantic v2 (`extra="forbid"` whitelist
validators), pytest + pytest-asyncio + testcontainers. **Zero new runtime dependencies.**

**Storage**: PostgreSQL. New tables in `account`: `account_bank_statement`,
`account_bank_statement_line`, `account_cash_rounding`, `account_lock_exception`,
`account_account_tag` (tax-grid tags, M2M to `account_tax_repartition_line`); **in the new
`analytic` addon**: `analytic_plan`, `analytic_account` (Odoo's own module boundary — confirmed by
`../odoo-19.0/addons/account/__manifest__.py` depending on `analytic`, not owning it); **in `base`**:
`res_currency_rate` (Odoo's own home for this table — `base` already owns `res_currency`, so this is a
same-addon addition, not a cross-addon extension).
New columns on models `account` already owns (plain `Field` additions — no DDL idiom needed):
`account_account.group_id` (Many2one); `account_move_line.discount` (Monetary);
`account_move.inalterable_hash` / `account_move.secure_sequence_number` /
`account_move.debit_origin_id` / `account_move.down_payment_origin_id` /
`account_move.invoice_cash_rounding_id`; `account_journal.restrict_mode_hash_table` (Boolean);
`account_payment_term.early_payment_discount_account_id` (Many2one);
`account_payment_term_line.next_month` (Boolean); `account_tax_repartition_line.tag_ids` (Many2many).
New columns on `res_company` (owned by `base`)
added via the **existing** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idiom from
`account/data/account_data.py::_PARTNER_FK_COLUMNS` (same file, new list):
`fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`, `purchase_lock_date` (all `DATE`),
`income_currency_exchange_account_id`, `expense_currency_exchange_account_id` (both `INTEGER`
referencing `account_account`), `fiscalyear_last_month`, `fiscalyear_last_day` (both `INTEGER`,
defaulting to `12`/`31`). `res_company.tax_rounding_method` **already exists**
(`dodoo/addons/base/models/res_company.py`, seeded by 005-localization) — the gap is that
`account_move._compute_tax_lines` never reads it (hardcodes round-globally); no new field needed
there, only a code fix.

**Testing**: `tests/accounting/` (existing 6 files + ~14 new files below), new `tests/analytic/`
(installs the new `analytic` addon standalone, plus `account`-side distribution-validation tests stay
in `tests/accounting/`), plus `tests/benchmarks/test_accounting_perf.py` (PERF-001/002/004) and an
extension of `tests/e2e/test_web_ui_a11y.py` for the new screens (bank statements, lock exceptions,
analytic accounts, tax report). Per `[[accounting-test-isolation]]`, any new test file that reads
`AccountReportTrialBalance`/`AccountReportGeneralLedger`/ledger-balance totals across a shared DB
(`test_reports_opening_balance.py`, `test_tax_report.py`) must run standalone, exactly like the
existing `test_reports.py`/`test_account_balance.py`.

**Target Platform**: Existing dodoo web server; no new deployment target.

**Project Type**: Web service + vanilla-JS SPA (existing monolith; all new UI is new *content* inside
`dodoo/addons/account/static/`, reusing the list/form/kanban view types 002/006 already shipped — no
new view type).

**Performance Goals**: PERF-001 Trial Balance / General Ledger opening-balance computation
(≤100,000 posted lines, 5-year history) adds < 150 ms over today's filtered-only query, via a
`(account_id, date)` composite covering the two date-range queries (today's filtered query plus the
new pre-`date_from` aggregate) rather than a per-account loop. PERF-002 reconciliation match-suggestion
(≤500 open items for one partner) returns in < 300 ms via a `(partner_id, reconciled)` partial index on
`account_move_line` (`WHERE reconciled = FALSE`) so the suggestion query never scans settled lines.
PERF-004 currency-rate lookup ("rate as of date") < 50 ms via a `(currency_id, rate_date DESC)` index
on `res_currency_rate`, queried with `rate_date <= :date ORDER BY rate_date DESC LIMIT 1`. PERF-003:
no regression permitted on the five report endpoints' existing response times for equivalent data
volumes (re-run `tests/benchmarks/` alongside the new suite).

**Constraints**: No new runtime dependencies. Migrations stay additive-only
(`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`) — per-journal sequence scoping is achieved
**without any schema change** by changing what string `action_post`/`account.payment.action_post` pass
as the `prefix` argument to the existing `get_next_sequence(conn, prefix, year)` (already keyed
`PRIMARY KEY (prefix, year)`): today `prefix` comes from the static `_JOURNAL_PREFIX[move_type]` dict;
after this feature it is the posting journal's own `code` column (already unique per journal, already
seeded with the *identical* literal strings `INV`/`BILL`/`CSH`/`BNK`/`MISC` `_JOURNAL_PREFIX` uses
today, so existing sequences and existing move `name`s are unaffected). Every new mutating workflow
(reconciliation write-off, bank statement continuity check, lock-exception grant) is a single
`env.dml_conn()` transaction with an existence/state re-check before mutating, matching
`AccountMove.action_post`'s own re-check-before-mutate shape — no new locking primitive. `account`
gains its **first** `security.py`/`validators.py`/`data/groups.py` (it currently has none — every
existing route is `auth="session"` with no group gate at all), but only the *new* sensitive actions
this feature adds (grant/revoke a lock exception, toggle a journal's hash-chain mode) are gated behind
the new "Accounting Manager" group; every pre-existing route's access behaviour is left exactly as it
is today (see Complexity Tracking — retrofitting group gates onto the whole addon is explicitly out of
scope for this feature).

**Scale/Scope**: 1 addon extended (`account`) + 1 new addon (`analytic`, 2 `BaseModel` classes,
mirroring Odoo's own `account` → `analytic` dependency) + 1 same-owner model addition (`base`'s
`res.currency.rate`) + 1 cross-addon `ALTER TABLE` extension (`account`→`res_company`, precedented).
7 new `BaseModel` classes in `account`/`base` + 2 in `analytic`, ~11 new columns across 7 existing
models, 8 new `res_company` columns, 39 functional requirements (FR-001…FR-039), 6 user stories
(P1×2: US1–US2; P2×2: US3–US4; P3×2: US5–US6), 9 ADRs (037–045), 6 contract files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. Code Quality**: Same linters/formatters as 001–007 (ruff, already configured for
  `dodoo/`/`tests/`); no new tooling. New models follow the existing `snake_case` table convention
  and the `dodoo/addons/account/{models,http,data,static}` layout already in place.
- [X] **II. Testing**: Unit tests cover pure-logic pieces with no DB (tax base-net-of-discount math,
  price-included extraction, due-date delay-type math, aged-bucket day math, hash-chain digest
  computation). Integration tests cover every cross-model workflow (reconciliation write-off +
  currency-aware residuals against a real Postgres container, bank-statement continuity + line
  reconciliation, lock-date rejection + exception grant, FX realized/unrealized gain-loss posting,
  opening-balance-inclusive report figures) per `tests/accounting/conftest.py`'s existing fixtures.
  E2E extends `test_web_ui_a11y.py` for the four new screens. Coverage thresholds match 001–007's CI
  gate (≥80% unit, 100% on the tax-computation and hash-chain critical paths).
- [X] **III. Security**: SEC-001…003 map to the new `account/security.py` "Accounting Manager" group
  gating lock-exception grant/revoke and hash-chain toggle (`require_groups`, the exact `hr`/`product`
  per-addon pattern), a `create_uid`/`create_date`/`end_date` audit row on every
  `account.lock.exception` (SEC-003), and automatic expiry enforced at read-time (the exception's
  `_get_active_lock_date` helper filters `end_date >= today`, never a background job — no scheduler
  exists in this codebase, per 007-inventory's own ADR-032 finding). OWASP review focuses on A01
  (a non-manager granting themselves a lock exception — closed by the group gate) and A08
  (data-integrity: the hash chain must make a tampered posted line's break detectable — closed by
  ADR-039's chain-verification function). Reconciliation write-offs and bank-statement lines reuse
  `AccountMove.action_post`'s existing balance-invariant path rather than writing ledger rows directly.
- [X] **IV. Performance**: PERF-001/002/004 targets and index strategy stated above (PERF-003's
  no-regression requirement enforced by re-running existing benchmarks alongside the new suite);
  `tests/benchmarks/test_accounting_perf.py` runs them in CI alongside 001–007's existing benchmarks
  (no regression on the five pre-existing report endpoints).
- [X] **V. Documentation**: ADR-037…045 filed below for every non-trivial design decision. Inline
  comments follow the WHY-only policy already demonstrated in `account_move.py`
  (`"""Round-globally tax computation (ADR-003)."""` is the precedent this feature's tax-engine
  comments follow, updated to cite ADR-040).
- [X] **VI. Accessibility**: ACC-001…003 restate WCAG 2.1 AA; no new view type is introduced — bank
  statements, lock exceptions, analytic accounts, and the tax report reuse the existing list/form
  types (`coa-list.js`/`account-form.js` are the direct precedents for the new list/form pairs).
- [X] **VII. Dependencies**: Zero new dependencies (Technical Context above). No CVE audit or
  lock-file change beyond what 001–007 already cover.
- [X] **VIII. CI/CD**: Reuses the existing CI pipeline; new test files plug into the same recursive
  `pytest` discovery already covering `tests/accounting/`.
- [X] **IX. Observability**: Every new mutating action logs a structured entry
  (`extra={"model": ..., "record_id": ..., "event": ...}`), the exact shape already used by
  `AccountMove.action_post`/`action_reverse`/`AccountPartialReconcile.reconcile_lines` — reconciliation
  write-offs, statement-line reconciliation, lock-exception grant/revoke, and hash-chain-break
  detection all log through this same convention (no new logging infrastructure).

*Initial gate: PASS. Post-design re-check: PASS — Phase 1 design (data model, contracts) stays within
the patterns validated above; see Complexity Tracking for the two decisions needing explicit
justification.*

## Architecture Decision Records

**ADR-037: Chart-of-accounts group auto-classification and reconcile-type constraints**

- **Decision**: `AccountAccount.create`/`write` (already overridden today to force `reconcile=True`
  for AR/AP) gains two more steps: (1) resolve `group_id` by finding the `account.account.group` whose
  `code_prefix_start <= code <= code_prefix_end` (numeric-string comparison on the account's `code`,
  matching Odoo's own `_compute_account_group`) and store it — a plain stored `Many2one`, recomputed on
  every `create`/`write` that touches `code`, not a live SQL join at read time; (2) reject
  `reconcile=True` when `account_type == "off_balance"`, and force `reconcile=False` (not just "allow
  false") for `asset_cash`/`liability_credit_card`/`off_balance` types, mirroring the existing
  AR/AP-forces-`True` block with a symmetric forces-`False` block for these three types.
- **Rationale**: `AccountAccount` already proves the "override `create`/`write`, re-derive a field,
  call `super()`" pattern for `reconcile`; extending the same two methods for `group_id` and the
  off-balance/cash constraint needs no new mechanism. Storing `group_id` (rather than computing it at
  every report query) means `account_report.py`'s existing `GROUP BY a.id, a.code, ...` queries can add
  `a.group_id`/`JOIN account_account_group` with no new per-row computation cost.
- **Alternatives rejected**: A live SQL `CASE`/join computing the group at report time — rejected
  because every one of the five report classes would need the same prefix-range logic duplicated;
  storing it once at write time is the existing codebase's approach to derived fields (e.g.
  `payment_state` is stored, not computed live, in `account_move.py`).

**ADR-038: Per-journal sequencing, cancel-state activation, reused-number-on-repost, and
draft-reversal option**

- **Decision**: (1) `AccountMove.action_post` and `AccountPayment.action_post` derive the sequence
  `prefix` from the posting journal's own `code` column (a fresh `SELECT code FROM account_journal
  WHERE id=:jid`) instead of the static `_JOURNAL_PREFIX[move_type]` dict — `account_sequence`'s
  existing `PRIMARY KEY (prefix, year)` already scopes correctly once `prefix` is journal-specific; no
  DDL change. (2) `action_post` becomes idempotent on `posted_before=True` moves: before calling
  `get_next_sequence`, it checks whether `name` is already set and the move's `date` still sorts after
  every other move in the same journal with a lower sequence number; if so it re-uses the existing
  `name` instead of allocating a new one (the exact re-post-after-draft-reset case FR-005 targets).
  (3) A new `AccountMove.action_cancel` classmethod transitions `draft → cancel` only (matching
  `STATE_CHOICES`'s existing, currently-unreachable `"cancel"` value and `action_reset_to_draft`'s
  existing `if rec["state"] == "cancel": raise ...` guard, which today can never trigger because
  nothing ever sets `cancel`). (4) `action_reverse` gains an `auto_post: bool = True` parameter; when
  `False` the reversal move is created and left in `draft` (the call to `cls.action_post(env,
  [rev_id])` is skipped) for the caller to review/adjust before posting manually — the HTTP action
  `/account/move/{id}/reverse` passes through a new `auto_post` body field, defaulting to `True` so
  existing callers (and existing tests) see no behaviour change.
- **Rationale**: Every one of these four changes edits an existing method's *inputs* or adds one new
  classmethod next to its siblings (`action_post`/`action_reset_to_draft`/`action_reverse` already
  live together in `account_move.py`) — no new file, no new table. Deriving the prefix from
  `journal.code` costs one extra `SELECT` already inside `action_post`'s existing per-move loop where
  `journal_id` is already fetched.
- **Alternatives rejected**: Adding a `sequence_id`/`ir.sequence`-style child model per journal
  (Odoo's actual mechanism) — rejected as new infrastructure disproportionate to the fix; `prefix`
  being a free-form string that already equals the seeded journal codes means no behavioural gap
  remains once the *source* of the prefix changes from a dict lookup to a column read. A `cancel`
  action that also cancels already-posted moves — rejected; Odoo's own `button_cancel` only cancels
  draft (or specifically reversed-with-cancel) entries, never a posted entry directly (that requires
  reversal, per FR-008/SC-005), so `action_cancel` only accepts moves currently in `draft`.

**ADR-039: Tamper-evident hash chain, line-level immutability, and fiscal lock dates/exceptions**

- **Decision**: `account_journal` gains `restrict_mode_hash_table` (Boolean, default `False`,
  per-journal opt-in). `account_move` gains `inalterable_hash` (Char) and `secure_sequence_number`
  (Integer, nullable). When `action_post` posts a move whose journal has hash mode on, it computes
  `sha256(previous_hash_in_this_journal + "|" + name + "|" + date + "|" + amount_total + "|" +
  sorted_line_tuples)` (the previous hash is the immediately-preceding secured move in the same
  journal, `NULL` → empty string for the first one) and stores it plus the next `secure_sequence_number`
  (a per-journal counter, reusing the `account_sequence` table with a distinct prefix
  `f"HASH/{journal.code}"`). A new `AccountMove.verify_hash_chain(env, journal_id)` classmethod
  recomputes every secured move's hash in sequence order and returns the first mismatch, if any (used
  by a new read-only `/account/journal/{id}/verify-hash-chain` route). `AccountMoveLine.write` gains
  the state check it currently lacks entirely: before calling `super().write()`, it reads each line's
  parent move's `state`/`inalterable_hash`, and rejects the write with the same `DodooError` message
  shape `AccountMove.write` already uses ("posted; cannot change: ...") whenever the move is `posted`
  — closing FR-008 without touching `AccountMove.write`'s own logic. `AccountMove.action_reset_to_draft`
  gains two more rejection conditions alongside its existing reconciled-lines check: `state == "cancel"`
  stays rejected as today, and now also `inalterable_hash is not None` or the move's `date` is on/before
  the applicable lock date (see below). Lock dates live as four new `res_company` columns
  (`fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`, `purchase_lock_date`, `DATE`, all
  nullable) added via the existing cross-addon `ALTER TABLE` idiom (same file,
  `account_data.py::_PARTNER_FK_COLUMNS` pattern, new list `_COMPANY_LOCK_COLUMNS`) — **not** a new
  `account.fiscal.year` model, matching Odoo 19's own move away from a separate fiscal-year record for
  this purpose (confirmed absent from the reference: lock enforcement in `../odoo-19.0/addons/account`
  reads `res.company` fields directly). A new `AccountLockException` model
  (`company_id`, `lock_date_field` [Selection: the four field names], `lock_date`, `user_id`
  [nullable Many2one — `NULL` = applies to any user], `journal_id` [nullable Many2one — `NULL` = any
  journal], `end_date`, `active`) is checked by a new `_get_effective_lock_date(env, company_id, field,
  user_id, journal_id, today)` helper: it returns the company's lock date for `field` unless an active
  (`end_date >= today`), matching (`user_id` or `NULL`) × (`journal_id` or `NULL`) exception exists, in
  which case it returns `None` (unlocked) for that one call. `AccountMove.action_post`/`write` both
  call this helper before touching a `posted`-bound move whose `date` falls at/before the relevant lock
  date; a lock hit does not hard-fail — per FR-032 it rewrites the move's own working `date` to
  `lock_date + 1 day` before proceeding and returns a warning string in the response payload (the HTTP
  layer surfaces it as a non-fatal `warning` key alongside `result: true`).
- **Rationale**: The hash chain reuses `account_sequence`'s existing atomic-upsert table for its own
  counter instead of inventing a second counter mechanism — a `HASH/<code>` prefix is just another row
  in the same table. Checking `inalterable_hash`/lock dates inside `action_reset_to_draft` (rather than
  a new gate function) keeps the single existing "can this move leave `posted`" choke point intact.
  Lock dates as plain `res_company` columns (not a model) match the reference implementation's own
  design and reuse the one precedent this codebase has for "addon B needs a column on a table addon A
  owns" — deviating to a new `account.fiscal.year` model here would be inventing structure the
  reference itself doesn't use.
- **Alternatives rejected**: A generic "immutable record" mixin applied to `account.move.line`
  broadly — rejected as speculative infrastructure for a single model; the same three-line state check
  `AccountMove.write` already has is sufficient and consistent. Storing the hash chain's "previous hash"
  as a live query (`MAX(secure_sequence_number)` lookup) instead of also storing
  `secure_sequence_number` — rejected; storing it makes `verify_hash_chain`'s ordering query an index
  scan instead of a per-move subquery.

**ADR-040: Discount, price-included tax, per-company rounding method, tax grids/report, debit notes,
and down payments**

- **Decision**: `account_move_line` gains `discount` (a `Monetary` percentage, 0–100, validated at the
  Pydantic boundary in a new `account/validators.py`). `_apply_price_defaults` (already the single
  place `price_subtotal` is derived from `price_unit × quantity`) is extended to multiply by
  `(1 - discount/100)` when `discount` is set, so every downstream consumer (tax computation, report
  totals) already sees the discounted subtotal with no second code path. `AccountMove._compute_tax_lines`
  is rewritten to: (a) use the line's stored `price_subtotal` (now discount-net) as `base` instead of
  re-deriving `base = debit - credit` from the raw line; (b) branch on each tax's existing
  `price_include` field — when `True`, extract the tax portion from the gross
  (`base_incl_tax = price_subtotal`; `tax = base_incl_tax - base_incl_tax / (1 + amount/100)` for
  `percent` taxes, the standard reverse-charge formula) instead of adding it on top; (c) read the
  posting company's **already-existing** `tax_rounding_method` field and, for `round_per_line`, round
  each product line's tax contribution before summing (today's single `round-globally` path stays the
  default and only path when the field is `round_globally`). `AccountTaxRepartitionLine` gains a
  `tag_ids` Many2many to a new `account.account.tag` model (`name`, `applicability` fixed to `"taxes"`
  for this feature — no G/L-account tagging use case is in scope) via a new junction table; a new
  `AccountReportTax` class in `account_report.py` aggregates posted invoice/bill tax amounts grouped by
  tag for a period, exposed at `/account/report/tax-report`. `AccountMove` gains `debit_origin_id`
  (Many2one to `account.move`, mirroring the existing `reversed_entry_id` field exactly) and a new
  `action_create_debit_note` classmethod: creates a new move of the **same** `move_type` as the
  original (not the refund type — a debit note on a vendor bill is itself an `in_invoice`, per Odoo),
  copies the original's lines verbatim (same signs — a debit note *adds* to the amount owed, unlike a
  reversal which flips signs), and sets `debit_origin_id`. Down payments are modelled as a new
  `display_type` value `"down_payment"` on `account_move_line` (extending the existing
  `DISPLAY_TYPE_CHOICES` list next to `"payment_term"`) plus a `down_payment_origin_id` Many2one on
  `account.move` pointing at the final invoice it will be deducted from; a new
  `AccountMove.apply_down_payments(env, invoice_id)` classmethod, called from `action_post` for
  invoice-type moves, finds any posted down-payment moves referencing `invoice_id` and inserts one
  negative `payment_term`-adjacent line reducing the invoice's AR balance by their total — reusing
  `_compute_payment_term_lines`'s existing imbalance-driven insertion rather than a new balancing
  mechanism.
- **Rationale**: Every piece attaches to a method that already owns exactly that computation
  (`_apply_price_defaults` for the subtotal, `_compute_tax_lines` for tax, `_compute_payment_term_lines`
  for the balancing AR/AP line) — no parallel computation path is introduced, which is what would make
  round-globally-vs-round-per-line or discount-before-tax bugs possible in the first place (today's bug
  class). Modelling a debit note as "same move_type, positive-copy, linked field" rather than a new
  document type reuses 100% of the existing invoice/bill posting, numbering, and reporting path.
- **Alternatives rejected**: A separate `account.debit.note` wizard model that only *stages* a debit
  note before creating the real move (Odoo's own Enterprise-adjacent implementation shape, via the
  small `account_debit_note` addon) — rejected as an extra model and extra round-trip for no behaviour
  difference once `account.move` itself already supports every field a debit note needs. A generic
  "credit memo" abstraction unifying credit notes and debit notes under one model — rejected; credit
  notes already exist and work via `_REVERSE_TYPE`/refund `move_type`s, so unifying would mean touching
  proven code for symmetry alone.

**ADR-041: Payment-term validation, early-payment-discount activation, and due-date fix**

- **Decision**: `AccountPaymentTermLine` gains a `create`/`write` classmethod override (the
  now-familiar pattern) that, whenever a line is added/changed with `value == "percent"`, re-sums all
  of the parent term's percent-type lines and raises `DodooError` if the total (including the line
  being written) does not equal exactly 100 — enforced at write time rather than only at use time, so
  an invalid term can never be saved. `_compute_due_date`'s `days_end_of_month_on_the` branch is fixed
  to compute the target month first (the invoice date's month, or the next month if a
  `days_next_month`-style flag is set — added as a new `Boolean` field `next_month` on
  `AccountPaymentTermLine`, default `False`) and then clamp the configured day within *that* resolved
  month's length, instead of always clamping within the invoice date's own month-end. `Account
  PaymentTerm.compute_installments` (the sole caller of the already-existing but dead
  `early_discount`/`discount_percentage`/`discount_days` fields) is extended to also return, per
  installment, `discount_date` (`invoice_date + discount_days`) and `discount_amount` (the installment
  amount reduced by `discount_percentage`) when `early_discount` is `True` on the parent term — these
  two new keys flow through to the existing invoice/payment JSON payloads with no schema change to the
  response shape's existing keys. `AccountPaymentTerm` gains one new column,
  `early_payment_discount_account_id` (Many2one to `account.account`, required only when
  `early_discount` is `True`), so `/account/payment/{id}/register` has somewhere to post the discount
  taken when a payment lands on or before `discount_date`.
- **Rationale**: `compute_installments` is already the single function every caller (invoice due-date
  display, the aged report's `invoice_date_due`) goes through, so adding the two discount keys here
  makes them available everywhere without a second lookup path. The 100%-sum constraint at write time
  (not post time) matches how `AccountAccount`'s reconcile constraint is already enforced at write
  time in this codebase.
- **Alternatives rejected**: Validating the 100% sum only when the term is *used* on an invoice (lazy
  validation) — rejected; it would let an already-broken term sit in the chart of payment terms
  indefinitely and fail unpredictably later, worse for the accountant than an immediate, clear error at
  creation time.

**ADR-042: Reconciliation write-offs/suggestions and the multi-currency rate/FX-gain-loss engine**

- **Decision**: `AccountPartialReconcile.reconcile_lines` gains two new optional parameters,
  `writeoff_account_id` and `writeoff_journal_id`; when the two lines' residuals don't exactly cancel
  and a write-off account is supplied, the method posts one additional two-line `account.move` (via the
  existing `AccountMove.create` + `action_post` path, journal defaulting to the company's `general`
  journal) crediting/debiting the write-off account for the leftover, then reconciles *that* move's new
  line against whichever original line still has a residual — so the accountant sees an ordinary posted
  journal entry for the write-off, not a special-cased row. A new
  `AccountPartialReconcile.suggest_matches(env, payment_id)` classmethod (no new model) queries open,
  unreconciled `payment_term` lines for the payment's partner ordered by `ABS(amount_residual - :amount)`
  ascending then by reference-string trigram similarity (`similarity(ml.name, :ref)`, `pg_trgm` — already
  available since PostgreSQL 15 ships it, enabled via one `CREATE EXTENSION IF NOT EXISTS pg_trgm`
  migration statement) and returns the top 10 candidates for the UI to present, not to auto-reconcile.
  `reconcile_lines` also starts actually populating and using the two already-declared-but-dead
  `debit_amount_currency`/`credit_amount_currency` fields: when either line's `currency_id` differs from
  the company currency, the residual comparison and the partial/full-reconcile-complete check both run
  in transaction-currency terms (`amount_currency`) rather than company-currency `amount_residual`,
  fixing the currency-blindness FR-022 flags. Multi-currency itself gains a new `base` model
  `ResCurrencyRate` (`currency_id`, `rate_date`, `rate` — company units per 1 unit of `currency_id`,
  matching Odoo's convention), manually entered via a new `/account/currency-rate` CRUD route (gated
  by the addon owning the acting user's session the same as every other route today — no new
  permission tier needed since rate entry is data-entry, not a control action). `AccountMove.action_post`
  is extended: for a move whose `currency_id` differs from its company's currency, it looks up the
  applicable rate (`rate_date <= move.date ORDER BY rate_date DESC LIMIT 1`) and, for every line lacking
  an explicit `debit`/`credit` already in company currency, derives them from `amount_currency × rate`
  — closing the "currency_id is decorative" gap. `AccountPartialReconcile.reconcile_lines` additionally
  detects, when both reconciled lines carry the same `amount_currency` but different company-currency
  `amount_residual` (because they were booked at different rates), the difference and posts it as a
  realized exchange gain/loss line to `res_company.income_currency_exchange_account_id` /
  `expense_currency_exchange_account_id` (the two new `ALTER TABLE`-added columns from ADR-039's list)
  via the same write-off-style helper move. A new `/account/currency/revalue` action
  (`AccountMove.revalue_currency_balances(env, company_id, as_of)`) implements the period-end
  unrealized step: for every open (`reconciled=False`) foreign-currency AR/AP line, it computes the
  difference between the line's booked company-currency value and its value at the `as_of` rate, posts
  one adjustment move dated `as_of` to the exchange accounts, and immediately creates the *reversing*
  move dated `as_of + 1 day` in draft (per FR-026's "reversible next period" — the reversal is created
  but left in draft for the accountant to post at the start of the next period, using
  `action_reverse(..., auto_post=False)` from ADR-038).
- **Rationale**: Routing the write-off and the realized-gain/loss postings through the *existing*
  `AccountMove.create`/`action_post` path (rather than raw INSERTs like `reconcile_lines` uses for its
  own residual bookkeeping today) means both get sequence numbers, balance validation, and — once
  ADR-039 lands — hash-chain coverage for free. Reusing `debit_amount_currency`/`credit_amount_currency`
  fields that already exist on the model (rather than adding new ones) is the minimal fix once their
  absence-of-use was the actual bug.
- **Alternatives rejected**: An automatic rate-provider integration (ECB feed, etc.) — explicitly ruled
  out in the spec's Clarifications; manual entry only. A dedicated `account.exchange.difference` model
  instead of a plain journal entry for the FX gain/loss posting — rejected; Odoo itself posts a normal
  `account.move` for this, and doing the same here keeps the write-off and FX-gain-loss code paths
  identical (both are "post a balancing move, then reconcile against it").

**ADR-043: Bank statements, continuity validation, statement-line reconciliation, and cash rounding**

- **Decision**: Two new `account`-owned models, `AccountBankStatement`
  (`journal_id`, `date`, `balance_start`, `balance_end_real`, `state` [`open`/`confirmed`],
  `company_id`) and `AccountBankStatementLine` (`statement_id`, `date`, `payment_ref`, `partner_id`,
  `amount`, `move_line_id` [nullable Many2one to `account.move.line` — set once reconciled]). A
  computed-at-read (not stored) `is_complete` check — `balance_start + SUM(line.amount) ==
  balance_end_real` — is evaluated by a new `AccountBankStatement.get_status(env, statement_id)`
  method and surfaced in the statement's read payload as `{"complete": bool, "computed_balance": ...}`;
  confirming a statement (`action_confirm`, `open → confirmed`) additionally checks the **prior**
  statement on the same journal (by `date`) has a `balance_end_real` equal to this one's
  `balance_start`, raising `DodooError` otherwise (FR-028's continuity rule). A new
  `AccountBankStatementLine.reconcile_against(env, line_id, move_line_ids)` action links the statement
  line to one or more existing (already-posted) `account.move.line` rows summing to its `amount`,
  setting `move_line_id` on an exact 1:1 match or, for a 1:N split, creating N `AccountBankStatementLine`
  child rows via the existing bulk-create path (no new "split" concept needed — a split is just
  multiple statement lines summing to the bank-reported transaction, exactly how Odoo's own statement
  import produces multiple lines from one imported transaction when needed). Cash rounding: a new
  `AccountCashRounding` model (`name`, `rounding` [Monetary, the increment, e.g. `0.05`],
  `rounding_method` [`up`/`down`/`half-up`], `strategy` [`add_invoice_line`/`biggest_tax`],
  `account_id` [the gain/loss account for `add_invoice_line`]); `AccountMove` gains an optional
  `invoice_cash_rounding_id` Many2one, applied in `action_post` right after tax computation: it rounds
  `amount_total` to the configured increment/method and, for `add_invoice_line`, inserts one adjustment
  line to `rounding.account_id` for the difference (for `biggest_tax`, it adjusts the largest existing
  tax line instead of adding a new one — reusing the tax-line update path `_compute_tax_lines` already
  has for its DELETE-then-INSERT cycle).
- **Rationale**: Placing both new models directly in `account` matches the reference implementation's
  own placement (`account.bank.statement`/`account.bank.statement.line` live in Odoo's `account`
  addon, not a separate module) — no addon-boundary question to resolve, unlike the `stock`/`stock_account`
  split 007-inventory had to make. Read-time `is_complete` (not a stored/triggered column) avoids a
  second write path that could drift from the lines it summarizes; `AccountAccount.get_balance` already
  established the "compute a summary on demand from source rows" convention this reuses.
- **Alternatives rejected**: Parsing specific bank file formats (CSV/OFX/CAMT.053) — explicitly out of
  scope per the spec's Clarifications; statement lines are created via the plain CRUD/bulk-create route,
  leaving a future file-import feature free to just call the same creation path. A stored/triggered
  `is_complete` boolean recomputed on every line insert — rejected as an unnecessary write-path
  duplication for a value only ever needed at read/confirm time.

**ADR-044: Financial-report opening balances, drill-down references, aged "not due" bucket, and
Balance Sheet earnings split**

- **Decision**: `AccountReportTrialBalance.get_report` and `AccountReportGeneralLedger.get_report` each
  gain a second query (reusing the same WHERE-clause builder minus the `date_from` condition, capped at
  `m.date < :date_from`) whose per-account `SUM(debit-credit)` becomes an `opening_balance` merged into
  each account's row before the filtered-period rows are added — a `UNION ALL`-free two-query approach
  (one pre-period aggregate, one in-period detail) chosen so the existing window-function running-balance
  query in the General Ledger needs only its window frame's *starting value* changed (`SUM(...) +
  :opening_balance` inside the same `OVER (...)` clause) rather than a rewritten query shape. All five
  report classes add `account_id` (already selected internally, just not returned) and, for the P&L/
  Balance Sheet/Aged reports, a representative `move_id` per line to their JSON payloads, and the SPA's
  `report-view.js` gains one click handler per report row that navigates to
  `#/accounting/journal-entries?account_id=...` (Trial Balance/Balance Sheet/P&L) or the specific move
  (Aged reports) — reusing the existing journal-entries list view and its existing `account_id` filter
  parameter (already supported, since General Ledger already filters by `account_id` today) rather than
  building a new drill-down view. `_bucket_for`'s aged-report boundary is fixed by introducing a fifth
  bucket, `"current"` (renamed from `_BUCKETS`'s four to five: `current, b_0_30, b_31_60, b_61_90,
  b_90_plus`), routed to whenever `days <= 0` instead of clamping negative days into `b_0_30` — a
  one-line change to `_bucket_for` plus extending the `_BUCKETS` tuple and the per-partner/grand-total
  dict comprehensions that already iterate it generically. `AccountReportBalanceSheet.get_report`'s
  current-year-earnings calculation is changed from `_pl_rows(env, _PL_TYPES, None, as_of, ...)`
  (all-time P&L) to `_pl_rows(env, _PL_TYPES, company_fiscal_year_start(as_of), as_of, ...)` — a new
  helper computing the start of the fiscal year containing `as_of` (from a new `res_company.fiscalyear_
  last_month`/`fiscalyear_last_day` pair, added via the same `ALTER TABLE` idiom as the lock-date
  columns, defaulting to `12`/`31` i.e. the calendar year, matching Odoo's own default) — so `cye` only
  ever reflects the current fiscal year, while the existing `equity_unaffected` account-type bucket
  (already in `_BS_GROUPS`, already seeded as "Retained Earnings" in `account_data.py`'s default COA)
  now correctly accumulates prior years' results once a fiscal-year-end closing procedure (a new,
  narrowly-scoped `AccountMove.close_fiscal_year(env, company_id, fiscal_year_end)` action posting one
  entry moving the prior year's `_pl_rows` net result into `equity_unaffected`) is run — closing FR-037
  without inventing a broader period-close subsystem. The new Tax Report (ADR-040) is exposed as a
  sixth report class, `AccountReportTax`, following the identical `_VirtualReport`/`get_report`
  contract every other report class already implements.
- **Rationale**: Every report change is additive to an existing query rather than a rewrite — the
  two-query opening-balance approach was chosen specifically so the already-correct in-period logic
  (grouping, rounding, sign-flipping per report) is untouched and only the account-level *starting
  point* changes. Renaming/extending `_BUCKETS` from four to five values is a pure data change; every
  consumer of `_BUCKETS` in `_aged_report` already iterates the tuple generically (`{b:
  Decimal("0") for b in _BUCKETS}`), so no per-bucket special-casing needs to be added anywhere.
- **Alternatives rejected**: A `UNION ALL` single-query approach for opening balance — rejected; it
  would require restructuring the General Ledger's window-function query entirely (the window's
  `ROWS BETWEEN UNBOUNDED PRECEDING` would then need to *exclude* the synthetic opening row from the
  per-line `debit`/`credit` columns while *including* it in the running total, a more error-prone query
  shape than adding a scalar offset to the window's starting value). A full period-close/lock-everything
  subsystem for FR-037 — rejected as disproportionate; `close_fiscal_year` is one narrowly-scoped action
  posting one entry, not a generalized period-management feature (fixed-asset/budget-style subsystems
  remain explicitly out of scope per the spec).

**ADR-045: Analytic accounting as a new addon, with distribution validation and roll-up reporting**

- **Decision**: A new addon, `dodoo/addons/analytic/`, depended on by `account` (added to `account`'s
  `__manifest__.py` `depends` list) — confirmed by reading
  `../odoo-19.0/addons/account/__manifest__.py` directly, whose own `depends` list includes `analytic`
  as a separate module `account` builds on, not a set of models `account` owns itself. Two models live
  there: `AnalyticPlan` (`name`, `company_id`) and `AnalyticAccount` (`name`, `code`, `plan_id`,
  `company_id`, `active`) — matching Odoo 19's own simplified (post-16.0) analytic model, where journal
  items carry a JSON `analytic_distribution` mapping `{analytic_account_id: percentage}` directly (this
  field **already exists** on `account_move_line`, currently unbacked and unvalidated) rather than
  generating a separate `account.analytic.line` row per posting. `AccountMoveLine.create`/`write`
  (already overridden for `_apply_price_defaults`, in `account`) gains a validation step: when
  `analytic_distribution` is set, every key must resolve to an active `analytic.account` row (a call
  into the new `analytic` addon, the same direction `account`→`analytic` Odoo itself has) and the
  values must sum to `100` (±0.01) — raising `DodooError` otherwise, closing "an arbitrary unvalidated
  value" from FR-038. A new `AccountReportAnalytic` class (in `account`, same `_VirtualReport` contract
  as every other report) aggregates posted `account_move_line.analytic_distribution` percentages × each
  line's `balance` grouped by `analytic_account_id` for a date range, exposed at
  `/account/report/analytic`.
- **Rationale**: A separate addon (not models folded into `account`) matches the reference
  implementation's own module boundary and this project's own established precedent — 007-inventory
  split `product`/`stock`/`stock_account` for exactly this kind of "a capability other addons may want
  independently of the consumer that motivated it" situation; analytic accounts are a plausible target
  for a future non-accounting consumer (e.g. project costing) the same way `product` was designed to be
  usable without `stock`. `analytic_distribution` as a JSON percentage-map directly on the journal item
  (no separate analytic-line table) is not a simplification invented for dodoo — it is Odoo 19's
  *actual* current design (the older `account.analytic.line`-per-posting model was Odoo's pre-16.0
  approach), so building the separate-line version here would be building an *older*, not more
  faithful, reference behaviour. Validating at `AccountMoveLine.write` time (the same choke point
  `_apply_price_defaults` already occupies) means an invalid distribution can never reach a posted line.
- **Alternatives rejected**: Folding `AnalyticPlan`/`AnalyticAccount` directly into
  `account/models/` — rejected once direct inspection of `../odoo-19.0/addons/account/__manifest__.py`
  confirmed Odoo 19 Community itself does not do this; matching the reference's actual module boundary
  takes priority over the marginal convenience of one fewer addon. A full `account.analytic.line`
  ledger mirroring `account.move.line` one-for-one — rejected as building Odoo's deprecated pre-16.0
  shape instead of its current one, which would fail the spec's own "match the Odoo 19 Community
  reference" standard rather than satisfy it.

## Project Structure

### Documentation (this feature)

```text
specs/008-accounting-parity/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── coa-journals-audit-trail.md   # ADR-037/038/039 (US3)
│   ├── invoicing-tax-engine.md       # ADR-040 (US1, US5)
│   ├── payment-terms.md              # ADR-041 (US1)
│   ├── reconciliation-currency.md    # ADR-042 (US2)
│   ├── bank-cash.md                  # ADR-043 (US2)
│   └── reports-analytic.md           # ADR-044/045 (US4, US6)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
dodoo/addons/account/
├── __manifest__.py                   # EDIT: "depends": ["base", "analytic"] (was ["base"])
├── security.py                       # NEW: GROUP_USER = "Accounting User",
│                                      #   GROUP_MANAGER = "Accounting Manager" (gates only the new
│                                      #   lock-exception and hash-chain-toggle actions — ADR-039)
├── validators.py                     # NEW: require_groups (hr/product pattern) + Pydantic models
│                                      #   for every new mutating route (DiscountLineCreate,
│                                      #   LockExceptionGrant, BankStatementCreate,
│                                      #   ReconcileWriteOff, CashRoundingCreate, AnalyticAccountCreate)
├── models/
│   ├── account_account.py            # EDIT: group_id resolution + off-balance/cash reconcile
│   │                                  #   constraint (ADR-037)
│   ├── account_account_tag.py        # NEW: account.account.tag (tax grids, ADR-040)
│   ├── account_journal.py            # EDIT: + restrict_mode_hash_table (ADR-039)
│   ├── account_move.py               # EDIT: journal-scoped sequencing + reused-number-on-repost +
│   │                                  #   action_cancel + auto_post reversal option (ADR-038);
│   │                                  #   hash-chain compute/verify + lock-date checks (ADR-039);
│   │                                  #   discount-net tax base + price_include + rounding-method
│   │                                  #   branch + debit_origin_id/action_create_debit_note +
│   │                                  #   down-payment display_type/apply_down_payments (ADR-040);
│   │                                  #   FX conversion at posting + revalue_currency_balances
│   │                                  #   (ADR-042); cash-rounding application (ADR-043);
│   │                                  #   close_fiscal_year (ADR-044)
│   ├── account_move_line.py          # EDIT: + discount field; write() state/hash/lock guard
│   │                                  #   (ADR-039); analytic_distribution validation (ADR-045)
│   ├── account_payment_term.py       # EDIT: 100%-sum constraint; days_end_of_month fix +
│   │                                  #   next_month field; early-discount activation (ADR-041)
│   ├── account_reconcile.py          # EDIT: write-off params; suggest_matches; currency-aware
│   │                                  #   residuals; realized FX gain/loss posting (ADR-042)
│   ├── account_sequence.py           # UNCHANGED (prefix source changes in callers, not here)
│   ├── account_lock_exception.py     # NEW: account.lock.exception (ADR-039)
│   ├── account_bank_statement.py     # NEW: account.bank.statement, account.bank.statement.line
│   │                                  #   (ADR-043)
│   ├── account_cash_rounding.py      # NEW: account.cash.rounding (ADR-043)
│   └── account_report.py             # EDIT: opening-balance queries (Trial Balance/GL); drill-down
│                                      #   ids; 5-bucket aged report; fiscal-year-scoped Balance
│                                      #   Sheet earnings (ADR-044); + AccountReportTax,
│                                      #   AccountReportAnalytic classes (ADR-040/045)
├── http/
│   └── __init__.py                   # EDIT/ADD: /account/move/{id}/cancel,
│                                      #   /account/journal/{id}/verify-hash-chain,
│                                      #   /account/journal/{id}/lock-exception (POST/DELETE),
│                                      #   /account/currency-rate (CRUD),
│                                      #   /account/currency/revalue,
│                                      #   /account/statement/* (CRUD + confirm + reconcile-line),
│                                      #   /account/cash-rounding (CRUD),
│                                      #   /account/analytic/{plan,account} (CRUD),
│                                      #   /account/report/tax-report, /account/report/analytic;
│                                      #   EDIT existing reverse/register routes for auto_post /
│                                      #   write-off params
├── data/
│   ├── account_data.py               # EDIT: + _COMPANY_LOCK_COLUMNS /
│   │                                  #   _COMPANY_EXCHANGE_COLUMNS ALTER TABLE lists
│   │                                  #   (ADR-039/042); CREATE EXTENSION IF NOT EXISTS pg_trgm
│   │                                  #   (ADR-042); + account_account_group seed rows for the
│   │                                  #   existing default COA (ADR-037)
│   ├── groups.py                     # NEW: seed_groups() for Accounting User/Manager
│   ├── indexes.py                    # NEW: account's first — ensure_indexes(env, ddl) per the
│   │                                  #   hr/stock convention; PERF-001/002/004 index DDL
│   └── i18n/{en,ar}.json              # EDIT: new UI strings (per [[i18n-per-addon-catalogs]])
└── static/
    ├── account-menu.js               # EDIT: + Bank Statements, Lock Exceptions, Analytic
    │                                  #   Accounts, Tax Report menu entries
    └── views/
        ├── invoice-form.js           # EDIT: + discount input per line, price_include indicator,
        │                              #   down-payment line, debit-note action button
        ├── report-view.js            # EDIT: + opening-balance row, drill-down click-through,
        │                              #   5-bucket aged columns, Tax Report + Analytic Report tabs
        ├── bank-statement-list.js    # NEW
        ├── bank-statement-form.js    # NEW (+ line reconciliation widget)
        ├── lock-exception-list.js    # NEW
        └── analytic-account-list.js  # NEW (list/form reuse existing generic types)

# NEW addon:
dodoo/addons/analytic/
├── __init__.py                       # imports http + models
├── __manifest__.py                   # {"name": "Analytic Accounting", "depends": ["base", "web"],
│                                      #   "application": False} — mirrors Odoo 19's own `analytic`
│                                      #   addon boundary (ADR-045)
├── security.py                       # no dedicated groups — analytic accounts are configured by
│                                      #   whichever depending app gates it (here: Accounting Manager,
│                                      #   defined in account/security.py, not here)
├── validators.py                     # AnalyticPlanCreate, AnalyticAccountCreate
├── models/
│   ├── __init__.py
│   ├── analytic_plan.py              # analytic.plan
│   └── analytic_account.py           # analytic.account
├── http/
│   └── __init__.py                   # CRUD is generic (jsonrpc dispatch); no dedicated routes needed
├── data/
│   ├── __init__.py
│   ├── ir_model_sync.py
│   └── i18n/{en,ar}.json              # NEW: UI strings (per [[i18n-per-addon-catalogs]])
└── static/
    └── views/
        └── analytic-account-list.js  # NEW (+ analytic-plan-list.js; reuse existing list/form types)

dodoo/addons/base/models/
└── res_currency.py                   # EDIT: + ResCurrencyRate model (currency_id, rate_date, rate)

# EDIT (existing files, not new addons):
CLAUDE.md                             # SPECKIT markers updated to point at this plan (Phase 1 step 4)

tests/accounting/
├── test_coa_groups.py                # NEW (ADR-037)
├── test_journal_sequencing.py        # NEW (ADR-038)
├── test_hash_chain_audit_trail.py    # NEW (ADR-039)
├── test_lock_dates_exceptions.py     # NEW (ADR-039)
├── test_invoice_discount_tax.py      # NEW (ADR-040)
├── test_debit_note_downpayment.py    # NEW (ADR-040)
├── test_tax_report.py                # NEW — run standalone (ADR-040/044,
│                                      #   [[accounting-test-isolation]])
├── test_payment_terms.py             # NEW (ADR-041)
├── test_reconciliation_writeoff.py   # NEW (ADR-042)
├── test_multi_currency.py            # NEW (ADR-042)
├── test_bank_statement.py            # NEW (ADR-043)
├── test_cash_rounding.py             # NEW (ADR-043)
├── test_reports_opening_balance.py   # NEW — run standalone (ADR-044,
│                                      #   [[accounting-test-isolation]])
├── test_aged_report_buckets.py       # NEW (ADR-044)
└── test_analytic_accounting.py       # NEW (ADR-045)

tests/analytic/
├── __init__.py
├── conftest.py                       # installs "analytic"
├── test_analytic_accounts.py
└── test_analytic_distribution.py     # validation (unknown account id, percentages ≠ 100) — the
                                       #   `account`-side write-guard tests live in
                                       #   test_analytic_accounting.py above; these cover the addon's
                                       #   own model-level behaviour

tests/benchmarks/test_accounting_perf.py   # NEW: PERF-001/002/004 (+ re-run existing suite, PERF-003)
tests/e2e/test_web_ui_a11y.py              # EDIT: + the four new screens' WCAG checks
```

**Structure Decision**: Almost everything is an in-place extension of `account`'s existing boundary,
plus one same-owner model in `base` (`res.currency.rate`, exactly where Odoo places it) and one
cross-addon `ALTER TABLE` extension of `res_company` (the established `account`→`res_partner`
precedent, now applied one addon over). The one exception is analytic accounting, which becomes its
own `dodoo/addons/analytic/` addon that `account` depends on — confirmed against
`../odoo-19.0/addons/account/__manifest__.py`'s own `depends` list, and consistent with this project's
007-inventory precedent of giving a reusable capability its own addon rather than folding it into the
consumer that first needed it. No new view type, no new core infrastructure — every ADR above attaches
to a method, table, or convention the codebase already has.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New `dodoo/addons/analytic/` addon (ADR-045) instead of folding `AnalyticPlan`/`AnalyticAccount` into `account/models/` | `../odoo-19.0/addons/account/__manifest__.py` itself depends on a separate `analytic` module — matching the reference implementation's actual module boundary, not an approximation of it | Folding the two models into `account` directly is fewer files short-term, but contradicts the reference source's own dependency list and this project's own 007-inventory precedent (`product`/`stock`/`stock_account`) of giving a reusable capability its own addon; a future non-accounting consumer of analytic accounts would otherwise have to depend on all of `account` to get them |
| `account` gains its first `security.py`/group gate (Accounting Manager), but only for the two new sensitive actions (lock-exception grant/revoke, hash-chain toggle) — every pre-existing route keeps today's session-only access | SEC-001…003 require lock exceptions to be grantable only by an authorized user and auditable; no group concept exists in `account` today to hang that gate on | Gating *every* existing account route behind new groups (full retrofit, matching `hr`'s two-tier model everywhere) — rejected as far outside this feature's audit scope; the spec's 39 findings never flagged missing role-based access on invoices/payments/reports as a gap, and retrofitting it now risks locking out existing test fixtures and workflows that assume session-only access, a regression this feature must not introduce (SC-007) |
| `AccountReportBalanceSheet`'s current-year-earnings fix (ADR-044) requires a `close_fiscal_year` action and two new `res_company` columns (`fiscalyear_last_month`/`fiscalyear_last_day`) — a small piece of period-close machinery | FR-037 requires current-year and prior-years' earnings to be reported separately, which is structurally impossible without *some* notion of where a fiscal year ends and *some* action that moves a closed year's result into `equity_unaffected` | A full period-close/lock-driven closing subsystem (auto-running at fiscal year end, generating closing/opening entries for every account) — rejected as reinventing budgeting/period-management scope explicitly excluded from this feature; `close_fiscal_year` is intentionally the single smallest action that makes FR-037's figures correct, triggered manually like every other action in this codebase (no scheduler exists) |
