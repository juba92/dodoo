# ADR-005: Add res.partner, res.company, res.currency to Base Addon

**Status**: Accepted | **Date**: 2026-06-07

## Context

The accounting module requires `res.currency` (functional currency), `res.company` (company context), and `res.partner` (customer/vendor). These did not exist in dodoo's base addon. They could be added to the account addon or the base addon.

## Decision

Add `res.currency`, `res.company`, and `res.partner` to `dodoo/addons/base/models/`. The account addon adds accounting-specific FK columns to `res.partner` via ALTER TABLE at install time.

## Consequences

- Matches Odoo's module architecture where these fundamental business objects live in `base`.
- Future modules (CRM, inventory, HR) can depend on `base` and get these models without depending on `account`.
- Circular dependency avoided: `base` has no dependency on `account`; `account` depends on `base`.
- Migration order at install: `res.currency` → `res.company` → `res.partner` (base columns) → account tables → `res.partner` accounting FK columns (ALTER TABLE).
- Defining them in the account addon was rejected as a layer violation.
