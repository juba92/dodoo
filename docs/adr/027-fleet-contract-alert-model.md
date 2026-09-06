# ADR-027: Fleet contract/alert model — stored expiry state + compute-on-read window

**Status**: Accepted | **Date**: 2026-09-06 | **Feature**: 006-human-resources

## Context

Reproduce Odoo `fleet`: leasing/insurance contracts with an expiry alert, odometer logs, a
seven-state vehicle lifecycle, and a driver linked to `hr.employee` — without accounting or
telematics, and without a scheduler.

## Decision

`fleet.vehicle.log.contract` stores `cost_type ∈ {leasing, insurance}`, `amount`, `start_date`,
`expiration_date`, `state ∈ {open, expired, closed}`. `get_expiry_alerts(env, window_days=None)`
returns contracts where `expiration_date <= today + window` (default from the module constant
`FLEET_ALERT_WINDOW_DAYS = 30`) or `state = 'expired'`, each with `days_left = expiration_date -
today` and its vehicle. `run_fleet_contract_expiry(env)` idempotently flips `open → expired` past
the date; exposed at `POST /fleet/cron/contract-expiry` (`Fleet Manager`).

`fleet.vehicle.odometer(value, date)`; `_latest_odometer(vehicle_id)` returns the row with
`max(date)`. A value below the previous max is accepted but flagged (`inconsistent = true`) and
logged at `warning`.

`fleet.vehicle.state` is a plain `Selection` of the seven lifecycle values with a guarded, logged
`action_set_state` (`vehicle_state_conflict` on stale state). `brand_id` is derived from
`model_id.brand_id` on create/write. A `driver_id` change appends the prior driver to
`former_driver_ids` (Json). `flag_reassignment_for_archived_drivers(env)` sets
`needs_reassignment = true` on vehicles whose driver employee has been archived.

## Consequences

- `search([('state','=','expired')])` is correct once the cron endpoint has run; the alert list is
  always correct via compute-on-read.
- Threat (A09, stale alert): the window is computed on read, so a missed cron run never hides an
  expiring contract from `get_expiry_alerts`.
- Rejected: pure compute-on-read for `state` (breaks stored-state queries); a scheduler daemon
  (same reasoning as ADR-024).
