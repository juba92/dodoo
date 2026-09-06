# Quickstart: Human Resources — Validation Guide

Runnable scenarios that prove the feature end to end. Assumes the dodoo dev setup from
`specs/005-localization-settings/quickstart.md` (PostgreSQL reachable via `DATABASE_URL` /
`TEST_DATABASE_URL`, Python 3.12, deps installed).

## 0. Install

```bash
# hr + fleet are built-in addons; installing fleet pulls hr (which pulls base, web)
python -m dodoo --install fleet          # or: --install hr  for HR only
```

Expected: migrations create every `hr_*` and `fleet_*` table; `post_install` seeds one
`resource.calendar` per company, a department tree, jobs, leave types, skill types + skills +
levels, recruitment stages (incl. one `is_hired_stage`), one appraisal template, contract types,
and Fleet brands + models; `res.groups` gains `HR Employee`, `HR Officer`, `HR Administrator`,
`Fleet Manager`; `ir_model` + `ir.rule` rows are present.

```bash
pytest tests/hr/test_migrations.py tests/fleet/test_migrations.py -q     # tables/columns present
```

## 1. P1 — Employee directory, org chart, contract, skills

```bash
pytest tests/hr/test_employee_directory.py tests/hr/test_org_chart.py \
       tests/hr/test_contract_state.py tests/hr/test_skills.py -q
```

Manual (SPA): log in as `admin` → **Employees** menu.
- Create Dept "Sales" then "Field Sales" (parent Sales); create Job "Account Executive"
  (expected 3). Create 3 employees; set one's manager, one's coach + a tag, link one to a user.
- Kanban + list show all 3; the Job card shows current headcount 3.
- Open an employee → 4 tabs (Personal / Work / Private / HR Settings); the org-chart widget shows
  the manager chain up and direct reports down. Setting an employee's manager to their own report is
  rejected.
- Add a Contract (wage, type, start date) → **Set state → Running**; it shows as the running
  contract. Back-date `date_end` and reload → shows **Expired**.
- Add two skills; a level from another skill type is not selectable; the same skill twice is
  rejected.
- Switch language to Arabic (Settings) → Employees screens render RTL with translated labels.

## 2. P2 — Time Off

```bash
pytest tests/hr/test_leave_duration.py tests/hr/test_leave_approval.py \
       tests/hr/test_leave_balance.py tests/hr/test_leave_accrual.py -q
```

Manual: as `admin`, create leave type "Paid Time Off" (unit=day, approval=manager). Add a public
holiday inside next week. Grant a 20-day allocation to an employee.
- As that employee: request 5 working days spanning a weekend + the holiday → duration shows the
  weekend and holiday excluded.
- As the manager: **Approve** → state `approved`; the employee's balance drops by the duration.
- As the employee: a second request overlapping the approved dates → rejected (`leave_overlap`).
- **Refuse** the approved leave → balance restored.
- Create an accrual allocation (1 day / month, cap 12); `POST /hr/cron/leave-accrual` twice →
  units increase once per elapsed month, never past 12 (idempotent).
- Open **Time Off → Calendar**: employee sees only their own; manager sees the team.

## 3. P2 — Recruitment

```bash
pytest tests/hr/test_recruitment_pipeline.py -q
```

Manual: **Recruitment** menu. Publish "Account Executive". Create two applicants via a source,
assign an interviewer. Drag applicant A across three stages (or use the keyboard "Move to…" menu).
Refuse applicant B with a reason → it leaves the pipeline. Move A to "Contract Signed"
(hired stage) → **Create Employee** → a new employee exists with A's data and links back;
run **Create Employee** again → same employee, no duplicate. No login user is created.

## 4. P3 — Appraisals

```bash
pytest tests/hr/test_appraisal_cycle.py -q
```

Manual: **Appraisals**. Launch an appraisal for an employee from the seeded template →
state `new`, feedback sections present for both sides. Advance `new → pending_confirmation →
confirmed`. As the employee, save self-feedback with visibility off → the manager cannot see it;
toggle visible → the manager can. **Set state → Done** → employee's next appraisal date = today +
12 months; the appraisal appears in the employee's history. Cancelling a non-done appraisal removes
it from "open" and does not touch the next date.

## 5. P3 — Referrals

```bash
pytest tests/hr/test_referral.py -q
```

Manual: **Referrals**. As an employee with a linked user, submit a referral for the published job →
an applicant is created (source = Employee Referral, linked to the referrer). Advance the applicant
through two stages → the referrer's referral view reflects the status. Referrer stats show
`total=1`. Convert the applicant to an employee → the referral shows `hired` and `hired=1`.
Un-publishing the job blocks new referrals but leaves this one visible.

## 6. P3 — Fleet

```bash
pytest tests/fleet/test_vehicle_lifecycle.py tests/fleet/test_odometer.py \
       tests/fleet/test_contract_alerts.py -q
```

Manual: **Fleet** menu (as a Fleet Manager). Create a vehicle from a seeded brand/model → starts
`new_request`; advance to `registered`. Assign an employee as driver → appears under that employee's
assigned vehicles. Add two odometer logs → latest reading shown; a lower reading is accepted but
flagged. Add an insurance contract expiring in 10 days and a leasing contract expired last month →
both appear in **Fleet → Alerts** with days-left. Add a service log → listed in the vehicle's
history. A non-Fleet-Manager creating a vehicle is denied.

## 7. Security & multi-company

```bash
pytest tests/hr/test_access_rules.py tests/fleet/test_access_rules.py -q
```

- A plain `HR Employee` user reads their own contract/private info but gets nothing for another
  employee's Private fields, contract, wage, or appraisal-as-employee.
- A manager sees their reports' pending leave + open appraisals; nothing for non-reports.
- With two companies, a user scoped to company A sees zero company-B records across all HR/Fleet
  models.
- Every state transition / approval / refusal emits a structured JSON log line with
  `correlation_id`, `actor_uid`, `model`, `record_id`, `from`, `to` (grep the test log capture).

## 8. Performance (CI benchmarks)

```bash
pytest tests/benchmarks/test_hr_directory_perf.py -q      # PERF-001: <500ms @ 2,000 employees
pytest tests/benchmarks/test_leave_balance_perf.py -q     # PERF-002: <300ms @ 5 years history
```

## 9. Accessibility & E2E

```bash
pytest tests/e2e/test_hr_ui.py tests/e2e/test_recruitment_ui.py tests/e2e/test_web_ui_a11y.py -q
```

Covers: Kanban/list/form/org-chart/calendar render; recruitment stage move by pointer **and**
keyboard; status conveyed by text+ARIA (not colour); WCAG 2.1 AA audit clean in LTR and RTL;
`<html lang dir>` correct.

## Definition of done (maps to spec Success Criteria)

| Check | Spec |
|-------|------|
| Fresh install → directory + org chart usable, no config | SC-001 |
| Zero cross-company records for a scoped user | SC-002 |
| Approval only via configured steps; balance = exact duration | SC-003 |
| Overlap / zero-duration requests rejected 100% | SC-004 |
| Applicant convert → exactly one employee, idempotent | SC-005 |
| Plain employee cannot read others' sensitive data | SC-006 |
| Manager sees only their team's pending items | SC-007 |
| Structured log for every transition type | SC-008 |
| Directory <500ms @2k; balance <300ms @5yr (CI) | SC-009 |
| Unit + integration + e2e for every workflow | SC-010 |
| a11y audit clean LTR + RTL; keyboard Kanban move | SC-011 |
| Fleet alert list surfaces 100% expiring/expired | SC-012 |
