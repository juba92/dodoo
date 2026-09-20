# Phase 0 Research: Customer Database

All Technical Context unknowns were resolved by direct inspection of the existing codebase
(`dodoo/addons/base`, `dodoo/addons/account`) and the Odoo 19 Community reference
(`../odoo-19.0/addons/account/models/partner.py`, `../odoo-19.0/odoo/addons/base/models/res_partner.py`).
No item required a guess; every decision below cites the file(s) that confirm it.

## D1: Does `res.partner` already have any of the fields this feature needs?

- **Decision**: Yes — three columns already exist on the `res_partner` table today, added by
  `account`'s own `account_data.py::_PARTNER_FK_COLUMNS` via raw `ALTER TABLE ... ADD COLUMN IF NOT
  EXISTS`: `property_account_receivable_id`, `property_account_payable_id`,
  `property_payment_term_id` (plus `property_supplier_payment_term_id`, out of scope — AP side).
  None of the four is read by any model class or route today; `property_account_receivable_id`/
  `property_account_payable_id` are read only via raw SQL from `account_move.py`'s down-payment
  logic (as an optional per-partner AR/AP account override, falling back to the company's default
  account type). `property_payment_term_id` is entirely dead — no reader anywhere.
- **Rationale**: Confirms this feature is substantially "wire up what's already there" rather than
  "add new infrastructure" for payment terms and AR/AP account overrides. Only `customer_rank`,
  `property_currency_id`, and the billing-address fields are genuinely new columns.
- **Alternatives considered**: N/A — this is a discovery, not a choice.

## D2: Where should new `res_partner` columns live — `base` or `account`, and as a declared `Field`
or a raw `ALTER TABLE` column?

- **Decision**: Split by ownership, matching Odoo's own module boundary exactly:
  - Billing address (`street`, `city`, `state_id`, `zip`, `country_id`) → declared `Field`s directly
    on `base`'s `ResPartner` class. Odoo's own `base` module (`odoo/addons/base/models/res_partner.py:263-276`)
    owns `street`/`zip`/`city`/`email`/`phone`/`vat` directly — general contact/address concepts, not
    accounting-specific. `base`'s `ResPartner` already carries `email`/`phone`/`vat` the same way.
  - `customer_rank`, `property_currency_id` → `account`'s existing raw-`ALTER TABLE` idiom
    (`_PARTNER_FK_COLUMNS`), not a declared `Field` on `base`'s class. Odoo's own `customer_rank` is
    defined in `account/models/partner.py:607` (`_inherit = "res.partner"`), i.e. conceptually owned
    by `account` even though it lives on the same DB row. This codebase has no `_inherit` mechanism;
    its proven substitute for "addon B needs a column on a table addon A owns" is the raw-SQL idiom
    already used for `property_account_receivable_id` etc. — confirmed as the established pattern
    by 008-accounting-parity's own `data-model.md` (line 6-9: "except where a column is added to a
    table owned by an addon that must not gain a reverse dependency ... those use the existing
    account_data.py-style raw ALTER TABLE idiom instead of a declared Field, exactly like account
    already does for res_partner").
- **Rationale**: Keeps `base` free of any accounting-specific concept (no reverse dependency,
  `base` still knows nothing about `account`), while address fields — which every consumer of
  `res.partner`, not just accounting, plausibly wants — live where general contact data already
  lives.
- **Alternatives considered**: All seven columns as declared `Field`s directly on `base`'s
  `ResPartner` — rejected; would make `base` own `customer_rank`/AR-currency-override, concepts with
  no meaning outside accounting, breaking the addon boundary this codebase already enforces
  elsewhere (`res_company`'s lock-date/FX columns are `account`-owned via the same idiom, not
  `base`-owned fields). A new `res.partner.customer` side-table — rejected, see plan.md ADR-046.

## D3: How does a partner get flagged as a "customer"?

- **Decision**: `customer_rank > 0` on the (now-extended) `res_partner` row — mirroring Odoo's
  `customer_rank` integer field exactly (`../odoo-19.0/addons/account/models/partner.py:607`,
  `default=0`). This feature only ever needs to distinguish "is/isn't a customer" (never "how many
  times has this partner been invoiced," which is what Odoo's own rank-incrementing logic tracks via
  `action_post` bumping the counter) — so `customer_rank` starts at `0`/`1` (set to `1` by the
  customer create/edit form) and this feature does not implement Odoo's auto-increment-on-invoice
  behavior, since no user story or functional requirement calls for it (an already-flagged customer
  stays flagged; nothing in this feature un-flags one).
- **Rationale**: Matches the reference model exactly as the user's request explicitly names it
  ("following Odoo's res.partner (customer_rank) model"), while keeping the *behavior* around the
  field (what sets/increments it) scoped to only what the spec requires.
- **Alternatives considered**: A plain `is_customer` Boolean — rejected once the user's request
  explicitly named `customer_rank`; a boolean would also lose Odoo's own forward-compatible
  precedent of a partner being independently a customer *and* a vendor via two separate rank
  columns (this feature adds only `customer_rank`; a future vendor-management feature can add
  `supplier_rank` via the identical idiom without touching this feature's code).

## D4: How is the outstanding AR balance computed and kept current?

- **Decision**: On demand, at read time, from `account_move`/`account_move_line`/`account_payment`
  — no stored/maintained column. See plan.md ADR-047 for the query shape
  (`ResPartner.get_ar_ledger`, mirroring `AccountAccount.get_balance`'s
  compute-a-summary-from-source-rows convention).
- **Rationale**: Already resolved in the spec's Clarifications session (2026-09-20); reconfirmed
  here against the codebase's own precedent (`AccountAccount.get_balance`,
  `AccountBankStatement.get_status`) — both already prove this exact shape works and is the
  established answer to "give the UI a derived number without a second write path to keep in sync."
- **Alternatives considered**: See spec.md Clarifications and plan.md ADR-047.

## D5: Does "default payment terms/currency from company config" require a new company-level
default field?

- **Decision**: No. `res_company.currency_id` already exists (`base/models/res_company.py:16`,
  required) and is the currency default a new customer falls back to when
  `property_currency_id IS NULL`. There is no company-level "default payment term" concept anywhere
  in this codebase today (no seeded/flagged default `account.payment.term` row), and introducing one
  is outside this feature's scope (FR-011 only requires that *when* a company default exists, it's
  used, and that per-customer overrides are always possible) — so a new customer's
  `property_payment_term_id` simply defaults to `NULL` (no term forced) unless the accountant picks
  one, which still satisfies FR-011's override requirement.
- **Rationale**: Avoids inventing new company-level configuration infrastructure the spec doesn't
  actually require; FR-011 is satisfied either way since "default" only needs to mean "whatever the
  company-level source says today," and today that source is empty for payment terms.
- **Alternatives considered**: Adding a new `res_company.default_payment_term_id` field — rejected
  as scope creep; no functional requirement or user story calls for company-wide payment-term
  configuration, only per-customer defaulting behavior, which `NULL`-means-unset already provides.

## D6: Should customer CRUD routes be gated behind an "Accounting Manager"/"Accounting User" group?

- **Decision**: No — customer create/edit/search/list/AR-ledger-view stay session-only auth, the
  same as every pre-existing `account` route.
- **Rationale**: `account/security.py`'s own docstring records the explicit 008-accounting-parity
  decision that pre-existing routes keep session-only access, and only genuinely sensitive control
  actions (lock-exception grant/revoke, hash-chain toggle, fiscal-year close) get the new
  "Accounting Manager" gate. Creating or viewing a customer record is ordinary data entry, not a
  control action — gating it would be an unrequested, out-of-scope access-control change (and risks
  breaking existing test fixtures/workflows that assume session-only access, per 008's own
  Complexity Tracking entry on this exact question).
- **Alternatives considered**: Gating the new AR-ledger endpoint specifically (since it exposes
  financial data) — rejected; every other financial report endpoint in this addon
  (`/account/report/*`, `/account/account/{id}/balance`) is already session-only with no group gate,
  so singling out the AR ledger would be inconsistent with its own siblings.

## D7: Generic `#/accounting/model/:model` route vs. a bespoke customer view

- **Decision**: Bespoke `customer-list.js`/`customer-form.js`. See plan.md ADR-048.
- **Rationale**: Verified by reading `web/static/views/form.js` directly — it is pure
  field-introspection (builds inputs from `ir.meta`, Save/Discard/Delete only; no support for an
  embedded computed panel or extra action buttons). User Story 3's AR-ledger view cannot be rendered
  by it. The four entities currently routed through the generic path in this codebase (bank
  statements, cash rounding, lock exceptions, analytic accounts) are all plain-CRUD in the SPA today
  — none of them needed a computed panel, unlike this feature's P1 requirement.
- **Alternatives considered**: See plan.md ADR-048.
