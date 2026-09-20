# ADR-051: Bespoke vendor list/form views mirroring the customer pair; dedicated `/account/vendor` create/update paths (not `/account/partner`) to avoid a validator collision

**Status**: Accepted
**Date**: 2026-09-20

## Context

Vendor Database needs the same kind of bespoke, computed-panel-capable UI 009-customer-database
already built for customers, plus a create/update entry point. 009's `POST`/`PATCH
/account/partner` routes are already bound to `create_customer`/`update_customer`, fixed to the
`CustomerCreate`/`CustomerUpdate` Pydantic models (`extra="forbid"`).

## Decision

Two new files, `dodoo/addons/account/static/views/vendor-list.js` and `vendor-form.js`, registered
in `web/static/app.js`'s `_ROUTES` table immediately after the existing customer routes and before
the generic `#/accounting/([^/]+)$` catch-all. `vendor-list.js` follows `customer-list.js`'s exact
shape; `vendor-form.js` follows `customer-form.js`'s field-input shape plus a read-only Accounts
Payable panel. Vendor create/update use **new, distinct** routes — `POST /account/vendor` and
`PATCH /account/vendor/{id}` — rather than reusing 009's `POST`/`PATCH /account/partner`, since a
vendor-shaped payload's `supplier_rank`/`property_supplier_payment_term_id` fields would be
rejected outright by `CustomerCreate`/`CustomerUpdate`'s `extra="forbid"` boundary, and a route can
only dispatch to one handler. `GET /account/partner/{id}` (read) stays the single shared route both
forms already use. `ResPartner.unlink` (009's guard) is **not** modified — already partner-generic,
already blocks deleting a vendor with posted bills/payments. A "Vendors" item is added to
`account-menu.js`'s existing "Vendors" section.

## Rationale

`web/static/views/form.js`/`list.js` remain pure field-introspection with no embedded-computed-panel
support, the identical constraint 009's ADR-048 already found — nothing about that gap is
AR-specific. The route-collision finding (separate `/account/vendor` path) is new to this feature,
since 009 had no second role to collide with when it chose `/account/partner` for customer
create/update.

## Alternatives Rejected

Reusing `/account/partner`'s existing `POST`/`PATCH` with a single Pydantic model widened to accept
every customer *and* vendor field — rejected; it would silently permit a customer-form submission
to also set `supplier_rank` and vice versa, weakening the `extra="forbid"` whitelist's precision.
A generic per-model "extra panel" plugin mechanism for `web/static/views/form.js` — rejected as
premature shared infrastructure, the same reasoning 009's ADR-048 already applied.

## Consequences / Threat Note

Two parallel create/update route families (`/account/partner` for customer, `/account/vendor` for
vendor) both operate on the same underlying `res.partner` table — a partner promoted to both roles
is edited via whichever route matches the role being changed, never re-created. Archiving remains
available regardless of financial history on either role (only hard deletion is guarded, by the
existing 009 `ResPartner.unlink` check).
