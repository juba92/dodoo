# ADR-021: Localization packages as in-process definitions + an apply service

**Status**: Accepted | **Date**: 2026-09-05

## Context

Odoo ships one installable `l10n_*` module per country. dodoo has no end-user-triggered runtime
module installer, and only Egypt is in scope.

## Decision

A package is a Python dict in `dodoo/addons/localization/packs/egypt.py`, registered in
`PACKS = {"EG": EGYPT_PACK}`. `service.apply_country_localization(env, company_id, code, *,
confirm_currency_change=False, extra_company_vals=None)` idempotently seeds a currency, taxes (with
repartition to the tax accounts), and Domestic/Export fiscal positions into the existing `account`
models, then writes the company defaults — all inside one connection + commit. Every create is
guarded by a `(company_id, name)` lookup, so re-applying is a no-op and switching back reactivates
archived rows.

## Consequences

- "Choose a country → configuration appears" without a dynamic module installer.
- All packs live in one addon that depends on `account`.
- A neutral country (no `PACKS` entry, e.g. `GB`) only sets `country_id`.
- Rejected: one auto-installed dodoo addon per country (needs a runtime installer + dep resolution).
