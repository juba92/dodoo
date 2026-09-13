# Phase 0 Research: Accounting Parity with Odoo 19 Community

No `[NEEDS CLARIFICATION]` markers remain in the Technical Context — every unknown was resolved by
reading the actual current source of `dodoo/addons/account` (and its `base`/`stock_account`/`product`
integration points) alongside the Odoo 19 Community reference, rather than by inference. This document
records the research findings that ground `plan.md`'s Technical Context and ADR-037…045, including two
places where direct source inspection **corrected** an assumption made during the spec's original
audit (the audit's FR-level conclusions still hold; only the precise root cause changed).

## D1: Per-journal sequence scoping needs no schema change

- **Decision**: Change what string `AccountMove.action_post`/`AccountPayment.action_post` pass as
  `get_next_sequence`'s `prefix` argument — from the static `_JOURNAL_PREFIX[move_type]` dict lookup to
  the posting journal's own `code` column.
- **Rationale**: `account_sequence` (`dodoo/addons/account/models/account_sequence.py`) is already
  `PRIMARY KEY (prefix, year)` with an atomic `INSERT ... ON CONFLICT DO UPDATE ... RETURNING last_no`
  upsert — it is already safe for concurrent posting and already scopes correctly by whatever string it
  is given. The seeded default journals' `code` values (`INV`, `BILL`, `CSH`, `BNK`, `MISC`,
  `account_data.py::_DEFAULT_JOURNALS`) are *already identical* to `_JOURNAL_PREFIX`'s values, so
  switching the source of the prefix string changes zero existing sequence numbers or move names.
- **Alternatives considered**: A per-journal `ir.sequence`-style child model (Odoo's actual mechanism)
  — rejected as new infrastructure the existing atomic-upsert table already makes unnecessary.

## D2: `STATE_CHOICES` already lists `"cancel"` — the gap is that nothing ever sets it

- **Decision**: Add `AccountMove.action_cancel` (draft → cancel only); do not add a new state value.
- **Rationale**: Direct reading of `account_move.py` shows `STATE_CHOICES` already includes
  `("cancel", "Cancelled")`, and `action_reset_to_draft` already has a dead-code guard
  (`if rec["state"] == "cancel": raise DodooError(...)`) that can never trigger today because no
  method ever transitions a move *into* `"cancel"`. This corrects the spec-drafting-stage audit's
  characterization ("no distinct Cancelled state exists") — the state and its downstream guard exist;
  only the transition into it is missing. FR-004 is satisfied by adding the one missing transition, not
  by extending the state enum.
- **Alternatives considered**: None — this is a factual correction, not a design choice.

## D3: `res_company.tax_rounding_method` already exists — the tax engine just never reads it

- **Decision**: Add the `round_per_line` branch to `AccountMove._compute_tax_lines`; do not add a new
  company field.
- **Rationale**: `dodoo/addons/base/models/res_company.py` already declares
  `tax_rounding_method = Selection(TAX_ROUNDING_CHOICES, default="round_globally")` (seeded by
  005-localization). `_compute_tax_lines`'s docstring even names its hardcoded behaviour
  `"""Round-globally tax computation (ADR-003)."""` and never queries `res_company` at all. This
  corrects the audit's framing ("rounding method is hardcoded... no per-company configuration
  exists") — the configuration surface exists; the engine ignores it. FR-015 is satisfied by making
  `_compute_tax_lines` branch on the existing field, not by adding one.
- **Alternatives considered**: None — factual correction.

## D4: `res.currency.rate` belongs in `base`, matching Odoo's own module boundary

- **Decision**: Add `ResCurrencyRate` as a new model inside `dodoo/addons/base/models/res_currency.py`
  (same file as `ResCurrency`), not inside `account`.
- **Rationale**: `res.currency` is already owned by `base` (`res_currency.py`), and Odoo's own
  `res.currency.rate` lives in `base` too — `account` is a *consumer* of currency rates, not their
  owner, in the reference implementation. Since this is a brand-new table (not an extension of a table
  `base` doesn't own), it is a same-addon addition, not a cross-addon `ALTER TABLE` case — simpler than
  ADR-042 originally assumed. `account` still owns 100% of the FX-conversion and gain/loss *logic* that
  consumes the table.
- **Alternatives considered**: Placing `ResCurrencyRate` inside `account` for locality — rejected;
  it would misplace ownership relative to the reference implementation for no benefit, and would block
  any future non-accounting consumer of currency rates from using it without a dependency on `account`.

## D5: The `account`→`res_partner` `ALTER TABLE` idiom generalizes cleanly to `res_company`

- **Decision**: Add the four lock-date columns, two exchange-gain/loss account columns, and two
  fiscal-year-end columns to `res_company` via the same raw-DDL list pattern
  `account_data.py::_PARTNER_FK_COLUMNS` already uses on `res_partner`.
- **Rationale**: `account_data.py` already contains a proven, in-production pattern: a list of
  `"ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS ..."` strings run inside `seed_account_data`,
  wrapped in a `try/except: pass` per statement (idempotent across repeated installs). `res_company` is
  owned by `base` exactly as `res_partner` is, so the identical pattern applies with zero new
  mechanism — confirmed by reading `res_company.py`'s own top-of-class comment, which *already*
  anticipates this: `"# ... The account-referencing company columns ... are added by the localization
  addon as plain INTEGER columns via DDL, mirroring account_data.py::_PARTNER_FK_COLUMNS, so base keeps
  no dependency on account."` — i.e., the codebase already documents this exact idiom as the intended
  mechanism for exactly this situation.
- **Alternatives considered**: A new `account.company.settings` side-table — rejected per the same
  reasoning 007-inventory's ADR-033 rejected it for `product.category`: an unnecessary join for values
  that belong on the record they configure.

## D6: Analytic accounting must reproduce Odoo 19's *current* (JSON-distribution) model, not the
pre-16.0 `account.analytic.line` ledger — and it lives in its own `analytic` addon, not inside `account`

- **Decision**: Validate the existing `analytic_distribution` JSON field on `account.move.line`
  against real `analytic.account` records; do not add a separate analytic-posting-line table. Put
  `AnalyticPlan`/`AnalyticAccount` in a **new `dodoo/addons/analytic/` addon** that `account` depends
  on, not inside `account/models/` directly.
- **Rationale**: Odoo versioned its analytic model twice; the *current* (19.0) design keeps a
  percentage-map JSON field directly on the journal item, which is exactly the shape
  `account_move_line.py` already has (`analytic_distribution = Json()`), just unvalidated and unbacked
  by real analytic-account records today. Building a separate `account.analytic.line` ledger would
  reproduce an *older* Odoo design, failing the spec's explicit standard ("match the Odoo 19 Community
  reference") rather than satisfying it. Separately, reading `../odoo-19.0/addons/account/__manifest__.py`
  directly during plan review showed its own `depends` list includes `analytic` as a module `account`
  builds on — Odoo 19 Community does **not** keep analytic models inside `account` itself. An earlier
  pass of this plan had folded `AnalyticPlan`/`AnalyticAccount` into `account/models/account_analytic.py`;
  that placement is corrected here to match the reference implementation's actual module boundary and
  this project's own 007-inventory precedent (`product`/`stock`/`stock_account`) for exactly this kind
  of "give a reusable capability its own addon" situation.
- **Alternatives considered**: A parallel `account.analytic.line` model for historical/audit purposes
  — rejected as scope beyond what FR-038/039 ask for (validation + roll-up reporting only). Folding the
  two models into `account` for fewer files — rejected once the reference `__manifest__.py` confirmed
  Odoo itself doesn't do this.

## D7: Bank statements and cash rounding live inside `account`, not a separate addon

- **Decision**: `AccountBankStatement`, `AccountBankStatementLine`, and `AccountCashRounding` are new
  models inside `dodoo/addons/account/models/`.
- **Rationale**: Unlike 007-inventory's `product`/`stock`/`stock_account` three-way split (driven by a
  real Odoo module boundary between `stock` and `stock_account`), Odoo's own `account.bank.statement`
  and `account.cash.rounding` live inside its `account` addon itself — there is no reference-implementation
  boundary to preserve here, so a new addon would be unjustified structural complexity.
- **Alternatives considered**: A separate `account_bank` addon mirroring the inventory feature's
  multi-addon pattern — rejected; no such split exists in the reference implementation this feature is
  matching.

## D8: `account` gaining its first `security.py` is scoped to only the two new sensitive actions

- **Decision**: Introduce `GROUP_USER`/`GROUP_MANAGER` (the `hr`/`product`/`stock` two-tier pattern)
  solely to gate lock-exception grant/revoke and hash-chain-mode toggling; leave every pre-existing
  route's access model (session-auth only, no group check) unchanged.
- **Rationale**: Confirmed by reading `dodoo/addons/account/http/__init__.py` in full: **zero** of its
  existing routes call `require_groups` (unlike `hr`'s `employees.py`, which calls it on nearly every
  mutating route) — `account` today has no group concept at all. The spec's SEC-001…003 requirements
  are specifically about the *new* lock-exception mechanism (must be grantable only by an authorized
  user, scoped, auditable), not a general access-control audit of the whole addon — retrofitting group
  gates onto invoices/payments/reports is outside the 39 findings this feature is scoped to fix and
  risks regressing existing workflows/tests that assume today's session-only access (see plan.md's
  Complexity Tracking).
- **Alternatives considered**: Full role-based-access retrofit across `account` — rejected as
  out-of-scope scope creep relative to the audited findings.
