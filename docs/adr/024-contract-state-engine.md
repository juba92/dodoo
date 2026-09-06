# ADR-024: Contract-state engine — explicit transition table + compute-on-read expiry

**Status**: Accepted | **Date**: 2026-09-06 | **Feature**: 006-human-resources

## Context

`hr.contract` moves through draft → running → expired → cancelled. Two requirements pull in
different directions: FR-012 wants explicit, audited manual transitions; FR-016 wants a running
contract past its end date to *show* as expired without anyone acting. dodoo has no scheduler
daemon.

## Decision

`state` is a stored `Selection(draft|running|expired|cancelled)`. A module-level
`_TRANSITIONS: dict[str, set[str]]` names the legal moves
(`draft→{running,cancelled}`, `running→{expired,cancelled}`, `{expired,cancelled}→draft`).
`action_set_state(env, ids, target, uid, expected_state=None)`:

1. reads the current state; if `expected_state` is given and differs → `contract_state_conflict`
   (FR-067a), no side effects;
2. rejects a move not in `_TRANSITIONS[current]` → `contract_transition_invalid`;
3. on `→running`, rejects a second running contract for the same employee →
   `contract_running_exists`;
4. writes the new state and emits a structured transition log (correlation id, actor, from, to).

Expiry is *also* derived: `_effective_state(row)` returns `expired` for a `running` row whose
`date_end < today`, and read / list / search surface that. `run_contract_expiry(env)` is an
idempotent service that persists the flip (`UPDATE … WHERE state='running' AND date_end < today`),
exposed at `POST /hr/cron/contract-expiry` for an external timer and called opportunistically when
a contract list loads. The stored value is the source of truth; the derived value only ever *adds*
`expired`, never contradicts a stored state.

## Consequences

- FR-012 (audited manual transitions) and FR-016 (derived expiry) stay consistent.
- `search([('state','=','running')])` and reports remain correct once the cron endpoint has run;
  between runs, list views still *display* `expired` via `_effective_state`.
- Threat (A04, self-service state abuse): every transition is group/relationship-checked server-side
  and from-state-guarded; the cron endpoint is `HR Administrator` only.
- Rejected: pure compute-on-read (breaks stored-state queries and the audit trail); a scheduler
  daemon (new dependency / process-model change for one nightly flip).
