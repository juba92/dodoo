# ADR-025: Time-off approval + accrual design

**Status**: Accepted | **Date**: 2026-09-06 | **Feature**: 006-human-resources

## Context

Reproduce Odoo `hr_holidays`: multi-step leave approval, calendar-aware duration, balance
computation, overlap validation, and allocations that can accrue over time — without Odoo's
milestone-based accrual-plan engine and without a scheduler.

## Decision

**Approval.** `hr.leave.type.approval_mode ∈ {no_validation, manager, hr, both}`. `hr.leave.state`:
`to_approve → (second_approval) → approved`, plus `refused` from any non-terminal state and from
`approved` (which releases the consumed balance). `action_approve(env, ids, uid,
expected_state=None)` resolves the required approver: the `res.users` linked to
`employee.manager_id`; if there is no manager, or the caller would be approving their own request,
it escalates to any user in `HR Officer` for the employee's company. Each call advances exactly one
step and logs it; `both` needs two distinct approving users. `expected_state` mismatch →
`leave_state_conflict` (FR-067a).

**Duration.** `_leave_duration(env, employee_id, date_from, date_to, unit)` runs one set-based
query: `generate_series(date_from::date, date_to::date, '1 day')` joined to the company
`resource_calendar_attendance` on weekday and anti-joined to `hr_public_holiday` ranges; returns a
day count, or an hour sum from the attendance `hour_to - hour_from`. Zero counted units →
`leave_zero_days`.

**Balance.** `allocated − taken − pending` via three aggregate queries keyed on
`(employee_id, leave_type_id)`. Over-balance requests are refused when
`leave_type.allow_negative = false`. Overlap: an `EXISTS` `tsrange` query on non-refused
`hr_leave` for the same employee.

**Accrual.** `hr.leave.allocation.mode ∈ {regular, accrual}`; accrual carries `accrual_rate`,
`accrual_period ∈ {day, week, month}`, `accrual_max`, `last_accrual_date`. `run_leave_accrual(env)`
adds `floor(periods_elapsed) * accrual_rate` capped at `accrual_max` and updates
`last_accrual_date` (idempotent). Exposed at `POST /hr/cron/leave-accrual` (`HR Administrator`).

## Consequences

- Meets PERF-002 (< 300 ms balance at 5 years) — no per-day Python loop.
- Threat (A04, approval escalation / self-approval): approver set is resolved server-side and the
  requester is never their own sole approver; every step is logged.
- Rejected: per-day Python duration loop (fails PERF-002); a stored balance column (drift, needs
  triggers dodoo lacks); Odoo multi-milestone accrual plans (out of scope per spec).
