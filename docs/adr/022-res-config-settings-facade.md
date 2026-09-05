# ADR-022: res.config.settings as an RPC facade

**Status**: Accepted | **Date**: 2026-09-05

## Context

The Settings screen needs read/write endpoints for language + country. The SPA already speaks
`execute_kw`. Odoo models this as a transient `res.config.settings`.

## Decision

`res.config.settings` exposes `get_values`, `set_values`, `set_user_lang` classmethods called via
`execute_kw`. It reads the caller via `get_uid()` (ADR-006). `set_values` does the admin check,
whitelist validation, an optimistic-concurrency check against `res_company.write_date` (echoed in
the payload), then applies all `res.company` field changes in a single `res_company.write(...)`;
a country change delegates to `apply_country_localization` (which also folds in the `lang` write).
The currency-conflict guard is a zero-write pre-check.

## Consequences

- Reuses the JSON-RPC surface; no bespoke REST route.
- dodoo's installer does not register `_abstract` models, so this is a concrete model with a
  vestigial `id`-only table that is never populated — the methods are stateless.
- Atomicity is guaranteed at the company-row level; pack seed rows are idempotent so a partial
  apply converges on re-run.
