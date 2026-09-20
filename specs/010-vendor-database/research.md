# Phase 0 Research: Vendor Database

All Technical Context unknowns were resolved by direct inspection of the existing codebase
(`dodoo/addons/base`, `dodoo/addons/account`), the completed 009-customer-database cycle (its
`plan.md`/`research.md`/`data-model.md`), and the Odoo 19 Community reference
(`../odoo-19.0/addons/account/models/partner.py`). No item required a guess; every decision below
cites the file(s) that confirm it.

## D1: Does `res.partner` already have any of the fields this feature needs?

- **Decision**: Yes — more than 009-customer-database's own D1 found. `account_data.py`'s
  `_PARTNER_FK_COLUMNS` already carries `property_account_payable_id` and
  `property_supplier_payment_term_id` (added ahead of need in an earlier cycle, per 009's own D1
  which flagged both as "out of scope — AP side" at the time). Neither is read or written by any
  Python code today (`grep` confirms zero references outside `account_data.py`'s own `ALTER TABLE`
  line). `property_account_payable_id` is however already *read* by `account_payment.py`'s
  `action_post` (the vendor-payment AR/AP-account-resolution branch, `partner_type == "supplier"`)
  — so only the *write* path (the vendor form) and `property_supplier_payment_term_id`'s read/write
  path are missing. Billing address (`street`/`city`/`state_id`/`zip`/`country_id`) and contact
  fields (`email`/`phone`/`vat`) already exist as declared `Field`s on `base`'s `ResPartner`
  (added by 009-customer-database) and are shared as-is — a vendor is the same partner row as a
  customer, just with a different rank column set.
- **Rationale**: Confirms this feature is almost entirely "wire up what's already there," even more
  so than 009 was — no new billing-address fields are needed at all (009 already added them), and
  one of the two `account`-owned columns this feature needs (`property_account_payable_id`) is
  already partially wired. Only `supplier_rank` is a genuinely new column.
- **Alternatives considered**: N/A — this is a discovery, not a choice.

## D2: Where should the new `res_partner` column live — `base` or `account`, and as a declared
`Field` or a raw `ALTER TABLE` column?

- **Decision**: `supplier_rank` (Integer, default 0) is added via `account`'s existing
  `_PARTNER_FK_COLUMNS` raw-`ALTER TABLE` idiom in `account_data.py` — the exact same idiom
  009-customer-database used for `customer_rank`, not a declared `Field` on `base`'s `ResPartner`
  class. No new `base`-owned fields are needed (D1).
- **Rationale**: Mirrors Odoo's own module boundary exactly — Odoo declares `supplier_rank` right
  next to `customer_rank` in `account/models/partner.py`
  (`../odoo-19.0/addons/account/models/partner.py:608`), i.e. conceptually owned by `account`, not
  `base`, for the identical reason 009's ADR-046 gives for `customer_rank`. 009's own D3 explicitly
  anticipated this: "a future vendor-management feature can add `supplier_rank` via the identical
  idiom without touching this feature's code" — confirmed true; `customer_rank`'s existing row in
  `_PARTNER_FK_COLUMNS` is untouched, only a new line is appended.
- **Alternatives considered**: A declared `Field` directly on `base`'s `ResPartner` — rejected for
  the same reason 009 rejected it for `customer_rank`: it would make `base` own an
  accounting-specific concept it has no reason to know about. A new `res.partner.vendor` side-table
  — rejected; duplicates the single-rank-column concept Odoo itself uses and this codebase already
  has proof for.

## D3: How does a partner get flagged as a "vendor"?

- **Decision**: `supplier_rank > 0` on the (now-extended) `res_partner` row — mirroring Odoo's
  `supplier_rank` integer field exactly (`../odoo-19.0/addons/account/models/partner.py:608`,
  `default=0`), the same shape 009 used for `customer_rank`. Set to `1` by the vendor create/edit
  form; this feature does not implement Odoo's auto-increment-on-bill behavior, matching 009's own
  scoping decision for `customer_rank` (D3) — no user story or functional requirement calls for
  tracking *how many* bills a vendor has, only whether the partner is/isn't a vendor. A partner may
  independently carry `customer_rank > 0`, `supplier_rank > 0`, both, or neither, on the same row
  (FR-015) — the two columns are read/written completely independently, never coupled.
- **Rationale**: Matches the reference model exactly as the user's request explicitly names it
  ("following Odoo's res.partner (supplier_rank) model"), consistent with how 009 already resolved
  the identical question for `customer_rank`.
- **Alternatives considered**: A plain `is_vendor` Boolean — rejected for the same reason 009
  rejected a boolean for `customer_rank`: the user's request explicitly names `supplier_rank`, and a
  boolean would lose Odoo's own precedent of independent customer/vendor rank columns on one row.

## D4: How is the outstanding AP balance computed and kept current?

- **Decision**: On demand, at read time, from `account_move`/`account_move_line`/`account_payment`
  — no stored/maintained column, exactly mirroring 009's `get_ar_ledger` (ADR-047) and the
  pre-existing `AccountReportAgedPayable._aged_report(env, "liability_payable", ...)` query shape
  (`account_report.py:557`), which already proves the identical "sum open `liability_payable`
  `amount_residual` per partner" computation works against real posted vendor-bill data. See
  plan.md ADR-050 for the new `get_ap_ledger` function's exact shape.
- **Rationale**: Already resolved in the spec's Clarifications session (2026-09-20); reconfirmed
  here against two independent existing precedents (`get_ar_ledger` for the customer side of the
  identical problem, and `AccountReportAgedPayable` for the vendor/AP side of the identical account
  type) — both already prove this exact "computed at read time" shape works for
  `liability_payable`-account data specifically, not just `asset_receivable`.
- **Alternatives considered**: See spec.md Clarifications and plan.md ADR-050.

## D5: Can `get_ar_ledger`'s existing `_status_and_balance(lines)` helper be reused as-is for the
AP side, or does it need a vendor-specific variant?

- **Decision**: Reused as-is, unmodified. `_status_and_balance` (`account_partner.py`) is already
  pure arithmetic over a list of plain dicts carrying `amount_residual`/`_raw_status` — it has no
  AR-specific assumption anywhere in its body (confirmed by reading it in full: no reference to
  `_AR_MOVE_TYPES`, `asset_receivable`, or any customer-only concept). Only the *query* that builds
  the `lines` list going in differs between AR and AP (different move types, different account
  type, different `partner_type` filter on `account_payment`).
- **Rationale**: Avoids a near-duplicate `_ap_status_and_balance` that would drift from the AR
  version over time; the whole point of splitting `_status_and_balance` out as a pure, DB-free
  function in ADR-047 was exactly to make it reusable/unit-testable independent of which query
  produced its input.
- **Alternatives considered**: A parallel `_ap_status_and_balance` copy — rejected as needless
  duplication of already-correct, already-unit-tested logic.

## D6: Do PERF-001/002's index needs require any new index, or do 009's existing indexes already
cover the AP-ledger query?

- **Decision**: No new index is needed. `get_ap_ledger`'s query filters `account_move` by
  `(partner_id, move_type)` and joins `account_move_line` on `(move_id) WHERE display_type =
  'payment_term'` — exactly the same two predicates 009's `idx_account_move_partner_type
  (partner_id, move_type)` and `idx_account_move_line_payment_term_move (move_id) WHERE
  display_type = 'payment_term'` (both in `account/data/indexes.py`, added for 009's PERF-002)
  already cover. Neither index is scoped to a specific `move_type` *value* — they index the column,
  not a value — so `in_invoice`/`in_refund`/`in_receipt` rows benefit identically to
  `out_invoice`/`out_refund`/`out_receipt` rows.
- **Rationale**: Confirmed by reading `indexes.py`'s existing DDL directly rather than assuming;
  avoids adding a redundant index that would only add write overhead with no read benefit.
- **Alternatives considered**: A vendor-specific partial index (e.g. scoped to
  `move_type = ANY(ARRAY['in_invoice','in_refund','in_receipt'])`) — rejected as unnecessary once
  the existing unscoped indexes were confirmed to already cover the AP query's predicates.

## D7: Does FR-006 (delete-guard) need a new or modified `ResPartner.unlink` check for vendors?

- **Decision**: No. `ResPartner.unlink` (`base/models/res_partner.py`, added by 009's ADR-048) is
  already partner-generic — it counts *any* `account_move`/`account_payment` row referencing the
  partner id, with no `move_type`/`partner_type` filter, so a vendor with posted bills or payments
  is already blocked from hard deletion by the existing guard with zero code changes.
- **Rationale**: Confirmed by reading the guard's SQL directly (`WHERE partner_id = :pid`, no type
  predicate). Building a second, vendor-specific guard would be pure duplication of logic that
  already covers this case.
- **Alternatives considered**: N/A — this is a discovery, not a choice.

## D8: Should vendor CRUD/search/AP-ledger routes be gated behind an "Accounting Manager" group?

- **Decision**: No — same as 009's D6 for the customer side: session-only auth, consistent with
  every pre-existing `account` route (`account/security.py`'s documented 008-accounting-parity
  decision that only genuinely sensitive control actions get the manager-group gate).
- **Rationale**: Vendor create/edit/search/list/AP-ledger-view is ordinary data entry, not a control
  action, identical in kind to the customer-side decision already made and validated in 009.
- **Alternatives considered**: See 009's research.md D6 — the same reasoning applies unchanged.

## D9: Generic `#/accounting/model/:model` route vs. a bespoke vendor view

- **Decision**: Bespoke `vendor-list.js`/`vendor-form.js`, mirroring `customer-list.js`/
  `customer-form.js` file-for-file (ADR-051). The generic route remains unable to render a
  computed AP-ledger panel, for the same reason 009's ADR-048/D7 already established for the AR
  panel — nothing about that constraint is AR-specific.
- **Rationale**: Consistency with the proven, already-reviewed customer-side pattern; no new
  investigation needed since 009 already answered this question for the structurally identical
  problem.
- **Alternatives considered**: See 009's research.md D7 — the same reasoning applies unchanged.
