# Implementation Plan: Human Resources

**Branch**: `006-human-resources` | **Date**: 2026-09-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-human-resources/spec.md`

## Summary

Add two addons — `dodoo/addons/hr/` (Employees, Contracts, Skills, Time Off, Recruitment, Appraisals,
Referrals) and `dodoo/addons/fleet/` (vehicles, drivers, contracts, alerts, services) — plus small
`base` / `web` extensions, reproducing the behaviour of the Odoo 19.0 Human Resources application
section on dodoo's existing stack: FastAPI routing, SQLAlchemy Core (async) via the `BaseModel`
classmethod ORM, Pydantic-style whitelist validation at the HTTP boundary, additive `MigrationRunner`
schema, `ir.rule` record rules, and the vanilla-JS SPA. `hr` depends on `base` + `web`; `fleet`
depends on `hr`. Neither depends on `account` (003) — wages and fleet amounts are `Monetary`
values in the company currency with no journal posting. The web client gains two generic,
metadata-driven view types (Kanban, Calendar) and an org-chart widget; each area contributes its own
application menu the way the `account` addon does. Four ADRs cover the contract-state engine, the
time-off approval + accrual design, the appraisal cycle model, and the fleet contract/alert model.

## Technical Context

**Language/Version**: Python 3.12; ES modules (vanilla JS, no framework) for the web client.

**Primary Dependencies**: FastAPI, SQLAlchemy Core (async) 2.0, asyncpg, argon2-cffi, Starlette
middleware — all already vendored. **Zero new runtime or dev dependencies.** No scheduler library:
time-based transitions (contract expiry, accrual, fleet alerts) are computed on read and/or advanced
by an idempotent `run_cron`-style service method invoked from a REST endpoint (ADR-024/025/027).

**Storage**: PostgreSQL via asyncpg. New tables (all created by the additive `MigrationRunner`,
`CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS`, no destructive migrations):
`hr_department`, `hr_job`, `hr_employee`, `hr_employee_category` (+ M2M `hr_employee_category_rel`),
`hr_contract`, `hr_contract_type`, `hr_skill_type`, `hr_skill`, `hr_skill_level`, `hr_employee_skill`,
`resource_calendar`, `resource_calendar_attendance`, `hr_public_holiday`, `hr_leave_type`,
`hr_leave_allocation`, `hr_leave`, `hr_recruitment_stage`, `hr_recruitment_source`,
`hr_applicant` (+ M2M `hr_applicant_interviewer_rel`), `hr_applicant_refuse_reason`,
`hr_appraisal`, `hr_appraisal_template`, `hr_appraisal_feedback_section`, `hr_appraisal_feedback`,
`hr_referral`, `fleet_vehicle_model_brand`, `fleet_vehicle_model`, `fleet_vehicle`,
`fleet_vehicle_odometer`, `fleet_vehicle_log_contract`, `fleet_vehicle_log_services`.
Additive columns: `res_users` gains nothing (employee link lives on `hr_employee.user_id`);
`res_company` unchanged. Per-area covering indexes seeded in each addon's `data/*.py`
(`idx_hr_employee_company_name`, `idx_hr_leave_employee_type_state`, `idx_hr_applicant_job_stage`,
`idx_fleet_log_contract_expiry`, …).

**Testing**: pytest + pytest-asyncio (existing harness, real PostgreSQL via testcontainers or
`TEST_DATABASE_URL`). Unit: contract-state transition table, leave duration vs. working calendar +
holidays, balance = allocated − taken − pending, accrual tick, overlap detection, appraisal
next-date computation, fleet expiry-window classification, whitelist validators. Integration
(real DB): migrations present; each workflow end to end over `execute_kw` + REST action routes;
record-rule enforcement per group (Employee / Officer / Administrator / Fleet Manager); multi-company
isolation; from-state precondition conflict (FR-067a). E2E (Playwright, extends `tests/e2e/`):
Employees Kanban/list/form/org-chart, Time Off calendar + approval, Recruitment Kanban stage move
(pointer + keyboard), RTL layout, a11y audit.

**Target Platform**: Linux server (single-process FastAPI/uvicorn); modern evergreen browser.

**Project Type**: dodoo addons — `dodoo/addons/hr/` + `dodoo/addons/fleet/` + minimal `base` / `web`
extensions.

**Performance Goals**:
- PERF-001: employee directory list/search first page (50 rows) < 500 ms at 2,000 employees, with
  name/department/job filters — served by `hr.employee.search_read` over an indexed query.
- PERF-002: time-off balance for one (employee, leave type) < 300 ms at 5 years of history — one
  aggregate query per component (allocated / taken / pending), no per-day Python loop for the common
  case; calendar day-count uses a set-based generate_series join.
- PERF-003: recruitment Kanban for a job with ≤ 500 applicants < 800 ms — single grouped query.
- PERF-004: fleet expiry-alert list < 500 ms at 1,000 vehicles / 5,000 contracts — single indexed
  query on `fleet_vehicle_log_contract.expiration_date`.
- PERF-005: no regression to 001–005 targets; CI benchmarks added under `tests/benchmarks/` for the
  directory search and the balance computation.

**Constraints**: single functional currency per company (from 003/005); Gregorian calendar; one
`resource.calendar` per company (per-employee calendars out of scope); accrual is fixed-rate-per-
period with optional cap (not Odoo multi-milestone plans); no chatter/mail, no email, no scheduler
daemon; static UI strings only through the 005 catalog. dodoo's ORM commits per `create`/`write`
(no multi-statement transaction primitive) — multi-row workflow steps are ordered so a partial
failure is re-runnable (idempotent guards), matching the `account` addon precedent.

**Scale/Scope**: SME. ~2,000 employees, ~50 departments, ~200 jobs, ~5 leave types, ~30 skills,
~6 recruitment stages, ~1 appraisal template, ~1,000 vehicles. ~32 new models, ~6 SPA view modules,
2 new generic view types, 4 ADRs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. Code Quality**: ruff (`E,F,I,N,W,UP`, line-length 100) + Black already enforced repo-wide;
  new JS follows the existing `textContent`-only ES-module style (no `innerHTML` for data). No dead
  code; commented-out code prohibited.
- [X] **II. Testing**: pytest-asyncio; ≥ 80% unit coverage overall, 100% branch coverage on the
  contract-state table, leave duration/balance/accrual, appraisal next-date, fleet expiry
  classification, from-state guards, and every whitelist validator. Integration tests hit real
  PostgreSQL; no new mocks (external-boundary mock ban respected — there are no external services).
- [X] **III. Security**: SEC-001–007 in spec. Whitelist validation at every `execute_kw` custom
  method and REST action (allowed field names, types, enums, numeric/date ranges). Group checks
  (`Employee` / `HR Officer` / `HR Administrator` / `Fleet Manager`) + relationship checks
  (manager-of, record owner) on every workflow action, re-checked server-side. `ir.rule` record
  rules for cross-employee sensitive-data isolation. PII kept out of logs (SEC-006). OWASP review:
  A01 (cross-employee exposure, approval bypass, self-approval), A03 (free-text feedback / candidate
  details / notes / seed data), A04 (approval-workflow escalation) — mitigations in research.md.
  4 ADRs filed (below).
- [X] **IV. Performance**: PERF-001–005 above, all measurable and in this plan. CI benchmarks for the
  two spec-named paths (directory search, balance computation). No speculative optimization —
  indexes justified by the query shapes in data-model.md.
- [X] **V. Documentation**: ADR-024…027 filed in `docs/adr/`. Inline comments explain WHY only.
  No planning/analysis prose in source files.
- [X] **VI. Accessibility**: WCAG 2.1 AA both directions (ACC-001–004). Kanban drag has a keyboard
  alternative (move-to-stage menu); org chart and calendar expose accessible names/structure;
  status never colour-only (text + ARIA). `<html lang dir>` already set by 005; new views inherit
  it. Extends `tests/e2e/test_web_ui_a11y.py`.
- [X] **VII. Dependencies**: zero new packages; no CVE-audit burden added; no lock-file change.
- [X] **VIII. CI/CD**: no CI pipeline exists in dodoo yet (noted in 003/005) — out of scope for this
  cycle; gates enforced locally via Black + ruff + pytest. New benchmark tests are runnable in the
  same harness.
- [X] **IX. Observability**: `dodoo.core.logging` structured JSON entries with `correlation_id`
  (from `CorrelationMiddleware`) for every state transition and approval/refusal action
  (FR-066): contract state, each leave approval step, appraisal state, applicant stage change,
  referral status change, vehicle state, and every from-state-precondition rejection (FR-067a).
  Entries carry `model`, `record_id`, `actor_uid`, `event`, `from`/`to` — never PII payloads.

*Initial gate: PASS. Post-design re-check: PASS (see end of Phase 1).*

## Architecture Decision Records

**ADR-024: Contract-state engine — explicit transition table + compute-on-read expiry**
- Decision: `hr.contract.state` is a stored `Selection(draft|running|expired|cancelled)`. A module-
  level `_TRANSITIONS: dict[str, set[str]]` names the legal moves (`draft→running`, `running→expired`,
  `running→cancelled`, `draft→cancelled`, `expired|cancelled→draft`). `action_set_state(env, ids,
  target, uid)` reads the current state, rejects an illegal or stale move (`DodooError("contract_
  state_conflict")`, FR-067a), enforces "≤ 1 running contract per employee" with a guard query, and
  logs the transition. Expiry is *also* derived: a running contract whose `date_end < today` is
  reported as `expired` by `_effective_state()` used in list/search/read, and a lightweight
  `run_contract_expiry(env)` service (idempotent) flips the stored value for reporting. No scheduler
  daemon — `run_contract_expiry` is exposed at `POST /hr/cron/contract-expiry` for an external timer
  and is also called opportunistically when a contract list is loaded.
- Rationale: mirrors Odoo's `hr.contract` state plus `_get_contract_state` cron without adding a
  scheduler; keeps FR-012 (manual transitions) and FR-016 (derived expiry) consistent — the stored
  value is the source of truth, the derived value only ever *adds* `expired`, never contradicts.
- Alternatives rejected: (a) pure compute-on-read (breaks `search([('state','=','running')])`
  correctness and the FR-012 audit trail); (b) a real cron daemon (new dependency / process model
  change, unjustified for one nightly flip).

**ADR-025: Time-off approval + accrual design**
- Decision: `hr.leave.type.approval_mode ∈ {no_validation, manager, hr, both}`. `hr.leave.state`
  machine: `to_approve → (second_approval) → approved`, plus `refused` from any non-terminal state
  and `approved→refused` (balance restored). `action_approve(env, ids, uid)` resolves the required
  approver set — `manager` = the `res.users` linked to `employee.manager_id` (FR-028); if none, or
  the requester would be their own approver, it escalates to any user in `HR Officer` for the
  employee's company. Each call advances exactly one step and logs it; `both` needs two distinct
  approving users. Duration is computed by `_leave_duration(env, employee_id, date_from, date_to,
  unit)`: a set-based query joining `generate_series(date_from, date_to, '1 day')` against the
  company `resource.calendar` working weekdays minus `hr_public_holiday` ranges, returning days or
  hours. Balance = `allocated − taken − pending` via three aggregate queries; a request over balance
  is refused when `leave_type.allow_negative = false`. Overlap = `EXISTS` query on non-refused
  `hr_leave` for the same employee with `tsrange` (`timestamp without time zone`, matching the
  `Datetime` field type) overlap. **Accrual**: `hr.leave.allocation.mode
  ∈ {regular, accrual}`; accrual carries `accrual_rate`, `accrual_period ∈ {day,week,month}`,
  `accrual_max`. `run_leave_accrual(env)` (idempotent, keyed on `last_accrual_date`) adds
  `floor(periods_elapsed) * accrual_rate` capped at `accrual_max`; exposed at
  `POST /hr/cron/leave-accrual`.
- Rationale: reproduces Odoo `hr_holidays` multi-step validation, `_get_number_of_days` calendar
  logic, and a simplified `hr.leave.accrual.plan` without the milestone engine or a scheduler.
- Alternatives rejected: per-day Python loop for duration (fails PERF-002 at 5-year history);
  storing balance as a column (drift risk, needs triggers); full Odoo accrual plans (out of scope
  per spec Assumptions).

**ADR-026: Appraisal cycle model — template instantiation + per-side feedback rows**
- Decision: `hr.appraisal.template` has ordered `hr.appraisal.feedback.section` rows and
  `default_frequency_months`. `action_launch` copies each section into `hr.appraisal.feedback` rows
  tagged `side ∈ {employee, manager}` on the new appraisal (state `new`). State machine
  `new → pending_confirmation → confirmed → done`, `* → cancelled` from any non-`done` state; each
  transition guarded (FR-067a) and logged. Feedback visibility: `hr.appraisal.feedback.is_visible`
  (default false); a read by the opposite side filters out `is_visible = false` rows in the model
  layer (not only the UI). `action_done` sets `employee.next_appraisal_date = date_close +
  interval(frequency)` where frequency resolves `employee.appraisal_frequency_months` →
  `department.appraisal_frequency_months` → `template.default_frequency_months`. History = 
  `search([('employee_id','=',id)], order='date_close desc')`; "open" = the single non-`done`,
  non-`cancelled` appraisal.
- Rationale: mirrors Odoo `hr_appraisal` (`hr.appraisal`, assessment notes, `assessment_note`
  visibility, `_compute_next_appraisal_date`) with free-text sections instead of surveys.
- Alternatives rejected: single JSON blob for feedback (kills per-row visibility + query); survey
  integration (out of scope).

**ADR-027: Fleet contract/alert model — stored expiry date + compute-on-read window**
- Decision: `fleet.vehicle.log.contract` stores `cost_type ∈ {leasing, insurance}`, `amount`,
  `start_date`, `expiration_date`, `state ∈ {open, expired, closed}`. `get_expiry_alerts(env,
  window_days=None)` returns contracts where `expiration_date <= today + window` (default
  `window_days` from a module constant `FLEET_ALERT_WINDOW_DAYS = 30`), each with `days_left =
  expiration_date - today` and the vehicle. `run_fleet_contract_expiry(env)` (idempotent) flips
  `state` to `expired` past the date; exposed at `POST /fleet/cron/contract-expiry`. Odometer:
  `fleet.vehicle.odometer(value, date)`; `_latest_odometer(vehicle_id)` returns the row with
  `max(date)`; a value below the previous max is accepted but flagged
  (`inconsistent = true`, logged). Vehicle `state` is a plain `Selection` of the seven lifecycle
  values with a logged `action_set_state` (guarded, FR-067a); `brand_id` is derived from
  `model_id.brand_id` on create/write.
- Rationale: matches Odoo `fleet` (`fleet.vehicle.log.contract.state`, `days_left`,
  `fleet.vehicle.odometer`, `fleet.vehicle.state`) without accounting or telematics.
- Alternatives rejected: computing expiry state purely on read (breaks
  `search([('state','=','expired')])`); a cron daemon (same reasoning as ADR-024).

## Project Structure

### Documentation (this feature)

```text
specs/006-human-resources/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions & OWASP review
├── data-model.md        # Phase 1 output — full entity model, states, indexes
├── quickstart.md        # Phase 1 output — validation guide
├── contracts/           # Phase 1 output
│   ├── hr-employees.md       # hr.employee/department/job/category/contract/skill RPC + REST
│   ├── hr-timeoff.md         # hr.leave(.type/.allocation), resource.calendar, cron endpoints
│   ├── hr-recruitment.md     # hr.applicant/stage/source/refuse-reason RPC + REST
│   ├── hr-appraisal.md       # hr.appraisal(.template) RPC + REST
│   ├── hr-referral.md        # hr.referral RPC + REST
│   ├── fleet.md              # fleet.* RPC + REST + cron endpoints
│   └── security-groups.md    # groups, ir.rule domains, menu gating
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
dodoo/addons/hr/
├── __init__.py                       # imports http, models; post_install → seed_hr_data
├── __manifest__.py                   # {"name": "Human Resources", "depends": ["base", "web"], "application": True}
├── models/
│   ├── __init__.py
│   ├── hr_department.py               # hr.department (parent_id hierarchy, manager_id, company_id)
│   ├── hr_job.py                      # hr.job (expected/current headcount, published)
│   ├── hr_employee.py                 # hr.employee (personal/work/private/hr-settings groups; manager/coach; user_id)
│   ├── hr_employee_category.py        # hr.employee.category (tag) + M2M
│   ├── hr_contract.py                 # hr.contract + _TRANSITIONS + action_set_state + run_contract_expiry (ADR-024)
│   ├── hr_contract_type.py            # hr.contract.type (nullable company_id)
│   ├── hr_skill.py                    # hr.skill.type / hr.skill / hr.skill.level / hr.employee.skill
│   ├── resource_calendar.py           # resource.calendar (+ attendance rows) — company working time
│   ├── hr_public_holiday.py           # hr.public.holiday (date range, nullable company_id)
│   ├── hr_leave_type.py               # hr.leave.type (unit, paid, approval_mode, allow_negative, allocation_required)
│   ├── hr_leave_allocation.py         # hr.leave.allocation (regular|accrual) + run_leave_accrual (ADR-025)
│   ├── hr_leave.py                    # hr.leave + state machine + _leave_duration + balance + overlap (ADR-025)
│   ├── hr_recruitment_stage.py        # hr.recruitment.stage (sequence, hired_stage)
│   ├── hr_recruitment_source.py       # hr.recruitment.source (incl. employee-referral value)
│   ├── hr_applicant.py                # hr.applicant + stage move + refuse + create_employee (idempotent)
│   ├── hr_applicant_refuse_reason.py  # hr.applicant.refuse.reason (global)
│   ├── hr_appraisal.py                # hr.appraisal + state machine + action_launch/done (ADR-026)
│   ├── hr_appraisal_template.py       # hr.appraisal.template + hr.appraisal.feedback.section
│   ├── hr_appraisal_feedback.py       # hr.appraisal.feedback (side, text, is_visible)
│   └── hr_referral.py                 # hr.referral (referrer_id, job_id, applicant_id, derived status/counts)
├── security.py                        # group + ir.rule seed helpers (Employee/Officer/Administrator)
├── validators.py                      # whitelist Pydantic v2 models for every REST/RPC action payload
├── http/
│   └── __init__.py                    # REST action routes + cron endpoints + static mount /hr/static
├── data/
│   ├── __init__.py
│   ├── ir_model_sync.py               # ensure ir_model rows exist for hr.* (ir.rule.model_id FK)
│   ├── groups.py                      # seed res.groups: HR Employee ⊂ HR Officer ⊂ HR Administrator
│   ├── rules.py                       # seed ir.rule domains (see contracts/security-groups.md)
│   ├── indexes.py                     # covering indexes (PERF-001..003)
│   └── seed.py                        # seed_hr_data: company resource.calendar, departments, jobs,
│                                      #   leave types, skill types+skills+levels, recruitment stages
│                                      #   (incl. hired), 1 appraisal template, contract types
└── static/
    ├── hr-menu.js                     # 5 application menus (Employees/Recruitment/Time Off/Appraisals/Referrals)
    └── views/
        ├── employee-kanban.js         # card view for hr.employee
        ├── employee-form.js           # 4-tab form + skills section + org-chart widget mount
        ├── org-chart.js               # bespoke widget (manager chain up + direct reports down)
        ├── contract-list.js
        ├── timeoff-calendar.js        # calendar view for hr.leave
        ├── timeoff-form.js            # request + approve/refuse actions
        ├── recruitment-kanban.js      # pipeline grouped by stage; keyboard move-to-stage
        ├── applicant-form.js
        ├── appraisal-form.js          # per-side feedback with visibility toggle
        └── referral-form.js

dodoo/addons/fleet/
├── __init__.py                       # imports http, models; post_install → seed_fleet_data
├── __manifest__.py                   # {"name": "Fleet", "depends": ["hr"], "application": True}
├── models/
│   ├── __init__.py
│   ├── fleet_vehicle_model_brand.py  # fleet.vehicle.model.brand (global)
│   ├── fleet_vehicle_model.py        # fleet.vehicle.model (brand_id)
│   ├── fleet_vehicle.py              # fleet.vehicle (state machine, driver_id → hr.employee, brand derived)
│   ├── fleet_vehicle_odometer.py     # fleet.vehicle.odometer (value, date, inconsistent)
│   ├── fleet_vehicle_log_contract.py # leasing|insurance, amount, expiration_date, state, get_expiry_alerts (ADR-027)
│   └── fleet_vehicle_log_services.py # service type, date, amount, notes
├── security.py                        # Fleet Manager group + ir.rule (driver reads own vehicle)
├── validators.py
├── http/__init__.py                   # REST actions + /fleet/cron/contract-expiry + static mount
├── data/
│   ├── __init__.py
│   ├── ir_model_sync.py
│   ├── groups.py                      # seed res.groups: Fleet Manager
│   ├── rules.py
│   ├── indexes.py                     # idx_fleet_log_contract_expiry, idx_fleet_odometer_vehicle_date
│   └── seed.py                        # seed_fleet_data: sample brands + models
└── static/
    ├── fleet-menu.js
    └── views/
        ├── vehicle-kanban.js
        ├── vehicle-form.js            # state, driver, odometer history, contracts, services
        └── fleet-alerts.js            # expiry-alert list

dodoo/addons/web/static/
├── views/
│   ├── kanban.js                     # NEW: generic metadata-driven Kanban view type (group-by field)
│   └── calendar.js                   # NEW: generic metadata-driven Calendar view type (date field)
├── app.js                            # EDIT: register #/hr/* and #/fleet/* routes + sidebar menus
│                                     #       (mirrors the existing _renderAccountingMenu special-case)
└── style.css                        # EDIT: .o-kanban / .o-calendar / .o-orgchart styles + [dir=rtl] rules

dodoo/addons/base/
├── models/ir_meta.py                 # (reference) ir.model rows now seeded by hr/fleet data/ir_model_sync.py
└── data/base_data.py                 # unchanged

docs/adr/
├── 024-contract-state-engine.md
├── 025-timeoff-approval-accrual.md
├── 026-appraisal-cycle-model.md
└── 027-fleet-contract-alert-model.md

tests/
├── hr/test_migrations.py                 # all hr_* tables + columns present
├── hr/test_employee_directory.py         # CRUD, headcount, tags, user link, company scope
├── hr/test_org_chart.py                  # manager chain / reports; cycle rejection
├── hr/test_contract_state.py             # transition table, one-running guard, derived expiry, conflict
├── hr/test_skills.py                     # level-belongs-to-type, no dup skill
├── hr/test_leave_duration.py             # calendar + public-holiday exclusion; days & hours; zero-day reject
├── hr/test_leave_approval.py             # each approval_mode; self-approval escalation; refuse restores balance
├── hr/test_leave_accrual.py              # accrual tick + cap; idempotent re-run
├── hr/test_leave_balance.py              # allocated−taken−pending; negative-balance reject; overlap reject
├── hr/test_recruitment_pipeline.py       # stage move, refuse+reason, hired-stage, create_employee idempotent
├── hr/test_appraisal_cycle.py            # launch/confirm/done/cancel; per-side visibility; next-date
├── hr/test_referral.py                   # published-only, applicant link, status, counts
├── hr/test_access_rules.py               # Employee/Officer/Administrator record-rule matrix; PII isolation
├── hr/test_validators.py                 # whitelist rejects unknown fields / out-of-range
├── fleet/test_migrations.py
├── fleet/test_vehicle_lifecycle.py       # state machine, brand derivation, driver link retention
├── fleet/test_odometer.py                # latest reading; lower-than-prior flagged
├── fleet/test_contract_alerts.py         # expiry window classification; days_left; run_contract_expiry
├── fleet/test_access_rules.py            # Fleet Manager vs Officer vs driver-reads-own
├── benchmarks/test_hr_directory_perf.py  # PERF-001 (< 500 ms @ 2,000)
├── benchmarks/test_leave_balance_perf.py # PERF-002 (< 300 ms @ 5 yr)
├── e2e/test_hr_ui.py                      # Kanban/list/form/org-chart, Time Off calendar+approve, RTL
├── e2e/test_recruitment_ui.py            # Kanban stage move by pointer AND keyboard
└── e2e/test_web_ui_a11y.py               # EXTEND: hr/fleet screens, WCAG 2.1 AA both directions

(unit+integration hr/fleet tests grouped under tests/hr/ and tests/fleet/ per the tests/accounting/
 and tests/localization/ precedent.)
```

**Structure Decision**: Two self-contained addons. `hr` (`depends: ["base", "web"]`) holds
Employees + Contracts + Skills + Time Off + Recruitment + Appraisals + Referrals as one addon —
Odoo splits these into ~8 modules, but dodoo has no runtime module-install-on-demand and the spec
fixes the delivered boundary at `hr` + `fleet`; the internal `models/` split keeps the sub-areas
separable. `fleet` (`depends: ["hr"]`) is the separate addon the spec mandates, coupling to `hr`
only through `fleet.vehicle.driver_id → hr.employee`. Reference/config models that Odoo places in
`resource` (`resource.calendar`) live in `hr` here (no separate `resource` addon), matching the
"fundamental objects live with their consumer" precedent from 003/005. The two new generic view
types go in `web` (reusable by any model, like `list.js` / `form.js`); the org-chart widget is
HR-specific and lives in `hr/static`. `ir.model` rows (needed for `ir.rule.model_id`) are seeded by
each addon's `data/ir_model_sync.py` because nothing in the framework populates `ir_model` today —
the same gap the 001 access-rule tests work around by hand.

## Complexity Tracking

No constitution violations. Two items worth noting, both already the lightest option:

| Decision | Why needed | Lighter alternative rejected because |
|----------|------------|--------------------------------------|
| `data/ir_model_sync.py` seeds `ir_model` rows in each addon | `ir.rule.model_id` is a FK to `ir_model`, but no framework code populates `ir_model`; 001's tests insert rows by hand | Adding a framework-level `ir_model` sync touches `core`/`installer` and is out of scope for a feature branch; a per-addon idempotent seed is contained and removable when the framework grows one |
| Cron-style service methods behind `POST /hr/cron/*` and `/fleet/cron/*` instead of a scheduler | Contract expiry, accrual, and fleet-contract expiry are time-based; dodoo has no scheduler and adding one changes the process model | A real scheduler daemon is a new dependency + deployment concern for three nightly idempotent flips; compute-on-read covers correctness, the endpoints let an external timer advance stored state |
