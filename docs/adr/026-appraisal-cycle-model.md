# ADR-026: Appraisal cycle model — template instantiation + per-side feedback rows

**Status**: Accepted | **Date**: 2026-09-06 | **Feature**: 006-human-resources

## Context

Reproduce Odoo `hr_appraisal`: a periodic appraisal with employee and manager feedback, each side
controlling its own visibility, a computed next-appraisal date, and a per-employee history — using
free-text feedback sections instead of surveys.

## Decision

`hr.appraisal.template` owns ordered `hr.appraisal.feedback.section` rows and
`default_frequency_months`. `action_launch(env, employee_id, template_id, uid)` creates an
`hr.appraisal` (state `new`) and copies each template section into two `hr.appraisal.feedback`
rows, `side ∈ {employee, manager}`.

State machine: `new → pending_confirmation → confirmed → done`; `* → cancelled` from any non-`done`
state. Each transition is guarded (`expected_state` mismatch → `appraisal_state_conflict`,
FR-067a) and logged.

Feedback visibility: `hr.appraisal.feedback.is_visible` (default false). `read` / `search_read`
drop rows where `is_visible = false` **and** `side != caller_side` in the model layer, not only the
UI (FR-042). The owning side always sees its own rows; writes are restricted to the owning side
(`feedback_wrong_side`).

`_resolve_appraiser(employee)` returns the manager's user, or — when the employee has no manager,
or would be their own appraiser — any `HR Officer` in the employee's company.

`action_done` sets `date_close = today` and
`employee.next_appraisal_date = today + interval(frequency_months)` where the frequency resolves
`employee.appraisal_frequency_months → department.appraisal_frequency_months →
template.default_frequency_months`. History = `search([('employee_id','=',id)],
order='date_close desc')`; "open" = the single non-`done`, non-`cancelled` appraisal.

## Consequences

- Per-row feedback keeps visibility and querying simple; no JSON blob.
- Threat (A01, feedback leak): the opposite side cannot read hidden feedback even via raw
  `execute_kw` — the filter is in the model, not the client.
- Rejected: a single JSON feedback blob (kills per-row visibility + queries); survey integration
  (out of scope).
