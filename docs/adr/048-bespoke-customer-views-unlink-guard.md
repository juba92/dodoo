# ADR-048: Bespoke customer list/form views, not the generic `#/accounting/model/:model` route; a delete guard mirroring `AccountMove.unlink`

**Status**: Accepted
**Date**: 2026-09-20

## Context

This codebase already routes several simpler accounting entities (bank statements, cash rounding,
lock exceptions, analytic accounts) through a generic `#/accounting/model/:model` → `web/static/
views/{list,form}.js` path. Those generic views are pure field-introspection with no support for
an embedded computed panel or extra action buttons. Customer Database's User Story 3 (P1) requires
an AR-ledger *view* (balance + history table with drill-down), which the generic form cannot
render. Separately, FR-006 requires blocking hard deletion of a customer with financial history.

## Decision

Two new files, `dodoo/addons/account/static/views/customer-list.js` and `customer-form.js`,
registered in `web/static/app.js`'s `_ROUTES` table ahead of the generic
`#/accounting/model/([^/]+)` patterns — the same "accounting-specific route before the generic
model route" ordering `#/accounting/chart-of-accounts`/`#/accounting/account/…` already use.
`customer-list.js` follows `coa-list.js`'s shape: fetch, client-side substring filter, New button,
archived toggle. `customer-form.js` follows `account-form.js`'s field-input shape plus one
additional read-only AR-ledger panel. A new `ResPartner.unlink` classmethod override
(`base/models/res_partner.py`) checks, per id, whether any `account_move` or `account_payment` row
has `partner_id = id`; if so it raises `DodooError`, otherwise delegates to `super().unlink()`.

## Rationale

Building bespoke views only where a domain-specific view genuinely differs from plain-CRUD (as
`coa-list.js`/`account-form.js`/`invoice-form.js` already do) keeps this consistent with the
codebase's own existing split, not a new pattern. The delete guard mirrors `AccountMove.unlink`'s
existing posted-move guard exactly — same message shape, same "check state/references, then
delegate to `super()`" structure.

## Alternatives Rejected

Extending the generic `web/static/views/form.js` with a per-model "extra panel" plugin mechanism —
rejected as new shared infrastructure disproportionate to one feature's need. A `ResPartner.unlink`
override living in `account` instead of `base` — rejected; `unlink` must live on the class
SQLAlchemy dispatch actually calls (`ResPartner` in `base`).

## Consequences / Threat Note

Archiving remains available for any customer regardless of financial history (only hard deletion
is guarded), so no collections/audit data is ever lost through this feature.

**Two deviations from the precedents cited above, found via live e2e testing (Playwright + real
axe-core scans against a running server), not by inspection alone:**

- `customer-list.js` cannot use the generic `search_read` RPC to fetch customers at all —
  `customer_rank` is a raw, undeclared column (ADR-046), so the domain compiler rejects
  `[["customer_rank", ">", 0]]`. It fetches from a new `GET /account/customers` route instead
  (contracts/customer-database.md).
- `coa-list.js`'s row-click pattern (the shape this ADR says `customer-list.js` "follows") turned
  out to have no keyboard-operable equivalent at all — no `tabIndex`, no keydown handler — unlike
  `web/static/views/list.js`'s generic renderer, which does (`tr.tabIndex = 0` + Enter/Space). A
  live a11y test against `#/accounting/customers` caught this. `customer-list.js` uses the generic
  renderer's proven pattern instead of `coa-list.js`'s. Likewise, `account-form.js`'s `_wrapField`
  never associates its `<label>` with its control (no `for`/`id`), which axe-core flagged live on
  `#/accounting/customer/new`; `customer-form.js` uses `web/static/views/form.js`'s `ff-${field}`
  id/`for` pattern instead. Both `coa-list.js` and `account-form.js` themselves likely carry these
  same two gaps — pre-existing, out of this feature's scope to fix, but worth flagging.
