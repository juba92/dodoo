# ADR-045: Analytic accounting as a new addon, with distribution validation and roll-up reporting

**Status**: Accepted
**Date**: 2026-09-13

## Context

Analytic accounting is a genuine Odoo 19 Community feature (`account` depends on a separate
`analytic` module, confirmed by reading `../odoo-19.0/addons/account/__manifest__.py` directly),
but dodoo had only an inert, unbacked `analytic_distribution` JSON field on `account.move.line`
with no analytic accounts, plans, or roll-up reporting (FR-038/039).

## Decision

A new addon, `dodoo/addons/analytic/`, depended on by `account`. Two models live there:
`AnalyticPlan` (`name`, `parent_id`, `company_id`) and `AnalyticAccount` (`name`, `code`,
`plan_id`, `company_id`, `active`) — matching Odoo 19's own simplified (post-16.0) analytic
model, where journal items carry a JSON `analytic_distribution` mapping
`{analytic_account_id: percentage}` directly rather than a separate `account.analytic.line` row
per posting. `AccountMoveLine.create`/`write` gains a validation step: when
`analytic_distribution` is set, every key must resolve to an active `analytic.account` row and
the values must sum to `100` (±0.01). A new `AccountReportAnalytic` class aggregates posted
`analytic_distribution` percentages × each line's `balance` grouped by `analytic_account_id`.

## Rationale

A separate addon matches the reference implementation's own module boundary and this project's
007-inventory precedent (`product`/`stock`/`stock_account`) for "a capability other addons may
want independently of the consumer that motivated it." `analytic_distribution` as a JSON
percentage-map directly on the journal item is Odoo 19's *actual* current design, not a
simplification invented for dodoo — the older `account.analytic.line`-per-posting model was
Odoo's pre-16.0 approach.

## Alternatives Rejected

Folding `AnalyticPlan`/`AnalyticAccount` directly into `account/models/` — rejected once direct
inspection of the reference `__manifest__.py` confirmed Odoo 19 Community itself does not do
this. A full `account.analytic.line` ledger — rejected as building Odoo's deprecated pre-16.0
shape instead of its current one.

## Consequences / Threat Note

Purely additive — the existing unbacked `analytic_distribution` field simply becomes validated
and usable; a distribution referencing an unknown or archived analytic account is now rejected
rather than silently stored.
