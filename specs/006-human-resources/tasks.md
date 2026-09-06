---
description: "Task list for Human Resources implementation"
---

# Tasks: Human Resources

**Input**: Design documents from `specs/006-human-resources/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec mandates "unit + integration + e2e coverage for every workflow"
(SC-010) and the constitution requires ≥ 80% unit / 100% critical-path branch coverage.

**Organization**: Tasks are grouped by the six user stories from spec.md so each is independently
implementable and testable. `hr` is one addon (US1–US5); `fleet` is a second addon (US6).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6; Setup / Foundational / Polish have no story label
- Paths are repository-relative. dodoo addons live under `dodoo/addons/`; tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Create `dodoo/addons/hr/` skeleton: `__init__.py` (imports `http`, `models`; async `post_install` → `seed_hr_data`), `__manifest__.py` (`{"name": "Human Resources", "version": "1.0.0", "depends": ["base", "web"], "application": True}`), empty `models/__init__.py`, `http/__init__.py`, `data/__init__.py`, `static/views/` dir
- [x] T002 Create `dodoo/addons/fleet/` skeleton: `__init__.py` (imports `http`, `models`; async `post_install` → `seed_fleet_data`), `__manifest__.py` (`{"name": "Fleet", "version": "1.0.0", "depends": ["hr"], "application": True}`), empty `models/__init__.py`, `http/__init__.py`, `data/__init__.py`, `static/views/` dir
- [x] T003 [P] Create test packages `tests/hr/__init__.py` and `tests/fleet/__init__.py`; add `tests/hr/conftest.py` + `tests/fleet/conftest.py` that register the addon models with `env.registry` and run `MigrationRunner` + `seed_*_data` once per module (mirror `tests/integration/test_access_rules.py` setup fixture)
- [x] T004 [P] Confirm `pyproject.toml` ruff/black globs already cover `dodoo/addons/hr` and `dodoo/addons/fleet` (no change expected); run `ruff check dodoo/addons/hr dodoo/addons/fleet` to verify the skeletons lint clean
- [x] T005 [P] File ADR files from plan.md text: `docs/adr/024-contract-state-engine.md`, `docs/adr/025-timeoff-approval-accrual.md`, `docs/adr/026-appraisal-cycle-model.md`, `docs/adr/027-fleet-contract-alert-model.md` (title / status / context / decision / consequences + one-line threat note each)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [x] T006 Create `dodoo/addons/hr/_audit.py` with `log_transition(logger, *, model, record_id, actor_uid, event, frm, to, company_id=None, level="info")` emitting the structured `extra=` shape from research.md D9 (no PII); used by every workflow method (FR-066/FR-067a)
- [x] T007 Create `dodoo/addons/hr/validators.py`: a `validate(model_cls, payload) -> model` helper (Pydantic v2, raises `DodooError("unknown_field")` on `ValidationError` from `extra="forbid"`) plus a `require_groups(env, uid, *names)` / `is_member(env, uid, name)` helper using the group-name membership query from `res.config.settings.is_admin`
- [x] T008 Create `dodoo/addons/hr/data/ir_model_sync.py`: `sync_ir_model(env, models: list[tuple[name, table]])` → `INSERT INTO ir_model (name, table_name) VALUES (:n,:t) ON CONFLICT (name) DO NOTHING` (fills the gap noted in research.md D4 / plan Complexity Tracking)
- [x] T009 Create `dodoo/addons/hr/data/indexes.py`: `ensure_indexes(env, ddl: list[str])` running `CREATE INDEX IF NOT EXISTS …` (pattern from `account_data.py::_INDEXES`)
- [x] T010 Create `dodoo/addons/hr/security.py`: seed `res.groups` `HR Employee` / `HR Officer` / `HR Administrator` (idempotent by `name`); `assign_hr_group(env, uid, level)` inserting `res_users_groups_rel` rows for the level and all ancestors; `seed_rules(env, rows)` inserting `ir.rule` (+ `ir_rule_group_rel`) idempotently with `_validate_domain` JSON
- [x] T011 Create `dodoo/addons/hr/data/groups.py` (calls `hr.security.seed groups`) and `dodoo/addons/hr/data/rules.py` (empty `HR_RULES: list` registry + `apply(env)` — per-model rule rows are appended in each story phase)
- [x] T012 Create `dodoo/addons/hr/data/seed.py`: `seed_hr_data(env)` orchestrator calling, in order, `sync_ir_model`, `groups.seed`, `ensure_indexes`, per-area seed helpers (stubs now), `rules.apply`; wire it from `hr/__init__.py::post_install`
- [x] T013 Create `dodoo/addons/hr/http/__init__.py` skeleton: `MountRegistry.get().add_mount("/hr/static", NoCacheStaticFiles(...), name="hr_static")` and a `_json_ok` / `_json_err` helper matching `account/http`
- [x] T014 Extend `dodoo/addons/base/http/__init__.py::core_info` to also return `hr_groups: list[str]` (the caller's HR group names) and `fleet_manager: bool` (used for client-side menu gating per contracts/security-groups.md)
- [x] T015 [P] Create generic Kanban view type `dodoo/addons/web/static/views/kanban.js`: `render(container, { model, groupBy, columns?, cardFields, moveEndpoint?, hash })` — `fields_get` + `search_read`, column layout, card click → form route, drag + keyboard "Move to…" menu calling `moveEndpoint`
- [x] T016 [P] Create generic Calendar view type `dodoo/addons/web/static/views/calendar.js`: `render(container, { model, dateStartField, dateStopField?, titleField, colorField?, hash })` — month grid, `search_read` in visible range, event click → form, arrow-key day nav
- [x] T017 [P] Add `.o-kanban`, `.o-calendar`, `.o-orgchart` styles + matching `[dir="rtl"]` overrides to `dodoo/addons/web/static/style.css` (WCAG 2.1 AA contrast tokens, no colour-only status)
- [x] T018 (BLOCKED on T041 `hr-menu.js` + US1 view modules) Register HR + Fleet routing in `dodoo/addons/web/static/app.js`: add `#/hr/*` and `#/fleet/*` rows to `_ROUTES`, `_paramsFromHash`, `_labelFromHash`; add `_renderHrMenu` / `_renderFleetMenu` (modelled on `_renderAccountingMenu`) dispatched from `_renderSidebar`; bump `CLIENT_BUILD`
- [x] T019 Create `dodoo/addons/fleet/security.py` + `dodoo/addons/fleet/data/groups.py`: seed `res.groups` `Fleet Manager` (idempotent); `assign_fleet_manager(env, uid)`; reuse `hr.security.seed_rules`
- [x] T020 [P] Create `dodoo/addons/fleet/validators.py` (same `validate` import from `hr.validators`) and `dodoo/addons/fleet/data/ir_model_sync.py` / `indexes.py` (import the `hr` helpers), `dodoo/addons/fleet/http/__init__.py` skeleton (`/fleet/static` mount), `dodoo/addons/fleet/data/seed.py` `seed_fleet_data(env)` orchestrator wired from `post_install`
- [x] T021 [P] Test: `tests/hr/test_migrations.py` and `tests/fleet/test_migrations.py` asserting every table + additive column from data-model.md exists after install (will be extended per story)

**Checkpoint**: addons install; groups/rules framework, generic views, routing, logging helper all ready.

---

## Phase 2b: Record-rule domain engine extension (ADR-028) — BLOCKING

**Discovered during implementation**: `dodoo.core.query.compile_domain` only supported flat,
literal, single-column domain leaves — no user context, no relational traversal — and
`_get_access_domain` failed *open* on error. The HR security model (FR-059…FR-064, SC-006,
SC-007) is built on `ir.rule` domains like `["employee_id.user_id","=","$uid"]`. Full core
extension chosen (user decision, 2026-09-06).

- [x] T145 File `docs/adr/028-record-rule-domain-engine.md` (context / decision / scope boundary / consequences + threat note)
- [x] T146 Extend `dodoo/core/query.py`: `compile_domain(..., *, context=None, resolve=None)` — `$uid` / `$company_id` / `$company_ids` / `$today` placeholder substitution (incl. inside `in`/`not in` lists), dotted-path leaves compiled to `head_fk IN (SELECT id FROM rel WHERE …)` (recursive, ≤ N hops), and `= None` / `!= None` → `IS NULL` / `IS NOT NULL`. Add `AccessEnforcer.build_context(env, uid)` in `dodoo/auth/access.py`; log (not swallow) in `get_merged_domain`
- [x] T147 Wire into `dodoo/core/models.py::search`: build context + a registry-backed `resolve` closure, pass both when compiling the rule clause; on `DomainError` from a malformed rule apply `sa.false()` (fail closed, Principle III/IX). Unit tests `tests/unit/test_query_rule_engine.py` (14 cases: placeholders, 1- and 2-hop relations, NULL ops, resolver-missing, combinators, fail-closed) — no DB
- [ ] T148 Integration test the engine end to end: seed an `ir.rule` on a real model with `["…user_id","=","$uid"]`, confirm a non-owner `search`/`search_read` returns 0 rows and the owner sees theirs; confirm a malformed rule denies. `tests/integration/test_rule_engine.py` (needs Postgres)

**Checkpoint**: `ir.rule` domains can express ownership, company scope, and manager-chain access.

---

## Phase 3: User Story 1 — Employee directory, org structure, contracts, skills (Priority: P1) 🎯 MVP

**Goal**: A working company directory (departments, jobs, employees, tags, manager/coach, org
chart, Kanban/list/form), plus per-employee contracts (draft→running→expired→cancelled) and skills.

**Independent Test**: quickstart.md §1 — on a fresh install create a department tree, a job, three
employees; verify card/list/form/org-chart, add + run a contract (see it as the running contract,
back-dated end → expired), add two skills (level-type + duplicate guards).

### Tests for User Story 1

- [x] T022 [P] [US1] Unit test the contract `_TRANSITIONS` table, one-running guard, `_effective_state` expiry derivation, and `get_running_contract` in `tests/hr/test_contract_state.py`
- [x] T023 [P] [US1] Unit test skill-level-belongs-to-type and no-duplicate-skill guards in `tests/hr/test_skills.py`
- [x] T024 [P] [US1] Integration test employee CRUD, `hr.job.no_of_employees` headcount, tag M2M, `user_id` uniqueness per company, and multi-company isolation in `tests/hr/test_employee_directory.py`
- [x] T025 [P] [US1] Integration test `get_org_chart` (manager chain up + direct reports down) and manager-cycle / department-cycle rejection in `tests/hr/test_org_chart.py`
- [x] T026 [P] [US1] Integration test the record-rule matrix for `hr.employee` / `hr.contract` (HR Employee vs Officer vs Administrator), sensitive-field drop in `hr.employee.read`, and deny-by-default for no-group users in `tests/hr/test_access_rules.py`
- [x] T027 [P] [US1] Integration test whitelist validators reject unknown fields and out-of-range values for employee/contract/department/job payloads in `tests/hr/test_validators.py`

### Implementation for User Story 1

- [x] T028 [P] [US1] `hr.department` model in `dodoo/addons/hr/models/hr_department.py` (parent_id hierarchy, `manager_id`, `company_id`, `active`, `complete_name` on read, cycle guard in `create`/`write`)
- [x] T029 [P] [US1] `hr.job` model in `dodoo/addons/hr/models/hr_job.py` (`expected_employees`, `no_of_employees` computed on read, `is_published`, `active`)
- [x] T030 [P] [US1] `hr.employee.category` model + M2M `hr_employee_category_rel` in `dodoo/addons/hr/models/hr_employee_category.py`
- [x] T031 [P] [US1] `hr.contract.type` model in `dodoo/addons/hr/models/hr_contract_type.py` (nullable `company_id`)
- [x] T032 [P] [US1] Skill taxonomy models `hr.skill.type` / `hr.skill` / `hr.skill.level` in `dodoo/addons/hr/models/hr_skill.py` (`level_progress` 0–100)
- [x] T033 [US1] `hr.employee` model in `dodoo/addons/hr/models/hr_employee.py`: all Personal/Work/Private/HR-Settings fields (data-model.md), `manager_id` cycle guard, `user_id` unique per `(user_id, company_id)`, `read()` override dropping sensitive fields for non-owner/non-Officer callers, `get_org_chart(env, employee_id)`, `resolve_current(env)` (uid from context) — depends on T028–T030
- [x] T034 [US1] `hr.contract` model in `dodoo/addons/hr/models/hr_contract.py`: `_TRANSITIONS`, `action_set_state(env, ids, target, uid, expected_state=None)` (illegal→`contract_transition_invalid`, stale→`contract_state_conflict`, one-running guard→`contract_running_exists`, `log_transition`), `_effective_state`, `get_running_contract`, `run_contract_expiry(env)` (idempotent), date/trial `create`/`write` guards — depends on T033, T031, T006
- [x] T035 [US1] `hr.employee.skill` model in `dodoo/addons/hr/models/hr_skill.py`: level-type match guard (`skill_level_mismatch`), unique `(employee_id, skill_id)` (`skill_duplicate`), denormalised `skill_type_id` — depends on T032, T033
- [x] T036 [US1] Export all P1 model classes from `dodoo/addons/hr/models/__init__.py` and confirm they register + migrate (extend `tests/hr/test_migrations.py`)
- [x] T037 [P] [US1] Add employee/department/job/contract/employee-skill validator models to `dodoo/addons/hr/validators.py` (shapes from contracts/hr-employees.md)
- [x] T038 [US1] REST routes in `dodoo/addons/hr/http/__init__.py`: `POST /hr/contract/{id}/set-state`, `POST /hr/cron/contract-expiry` (Administrator-gated), `GET /hr/employee/{id}/org-chart`; each parses via `validate(...)`, checks groups via `require_groups`, returns the contract's `{result|error}` envelope — depends on T034, T037
- [x] T039 [US1] Append P1 `ir.rule` rows to `dodoo/addons/hr/data/rules.py` (`hr.employee`, `hr.contract`, `hr.job`, `hr.employee.category`, catalogs `hr.contract.type` / `hr.skill*`; deny-by-default `[["id","=",0]]` on `hr.employee`/`hr.contract`) per contracts/security-groups.md
- [x] T040 [US1] Implement P1 seed in `dodoo/addons/hr/data/seed.py`: one `resource.calendar` per company is NOT here (US2) — seed a "Sales / Field Sales" department tree, ~4 jobs, contract types (Permanent/Fixed-term/Internship/Part-time), skill types + skills + levels; register `sync_ir_model` entries for P1 models; add P1 indexes to `dodoo/addons/hr/data/indexes.py` (`idx_hr_employee_company_name`, `_name_pattern`, `_department`, `_job`, `_manager`, `uq_hr_employee_user_company`, `idx_hr_contract_employee_state`, `idx_hr_contract_date_end`, `idx_hr_job_*`, `idx_hr_department_*`, `uq_hr_employee_skill`)
- [x] T041 [P] [US1] `dodoo/addons/hr/static/hr-menu.js` — the 5 application menus (Employees / Recruitment / Time Off / Appraisals / Referrals) with `requires` gating keys; populate the **Employees** section hashes (`#/hr/employees`, `#/hr/contracts`)
- [x] T042 [P] [US1] `dodoo/addons/hr/static/views/employee-kanban.js` — card view via the generic `kanban.js` (`model:"hr.employee"`, `groupBy` none, card = name/photo/job/department)
- [x] T043 [P] [US1] `dodoo/addons/hr/static/views/org-chart.js` — bespoke accessible nested-`<ul>` widget (manager chain up, direct reports down) calling `GET /hr/employee/{id}/org-chart`
- [x] T044 [US1] `dodoo/addons/hr/static/views/employee-form.js` — 4 tabs (Personal/Work/Private/HR Settings) via `fields_get`, skills section grouped by skill type, mounts `org-chart.js` — depends on T042, T043
- [x] T045 [P] [US1] `dodoo/addons/hr/static/views/contract-list.js` — list + a "Set state" control calling `POST /hr/contract/{id}/set-state` with `expected_state`
- [x] T046 [US1] Wire `#/hr/employees`, `#/hr/employee/:id` (+ `/new`), `#/hr/contracts` routes and the Employees sidebar section into `dodoo/addons/web/static/app.js`; bump `CLIENT_BUILD` — depends on T041, T044, T045
- [x] T047 [US1] Add contract-transition + conflict `log_transition` calls (FR-066/FR-067a) throughout `hr_contract.py`; assert log shape in `tests/hr/test_contract_state.py`
- [x] T048 [US1] E2E `tests/e2e/test_hr_ui.py` — Employees Kanban/list/form/org-chart render; create employee; add + run contract; add skills; Arabic RTL layout
- [ ] T049 [US1] Extend `tests/e2e/test_web_ui_a11y.py` with the Employees screens (WCAG 2.1 AA, keyboard nav, `lang`/`dir`, no colour-only status)

**Checkpoint**: US1 fully functional and independently testable — the MVP.

---

## Phase 4: User Story 2 — Time Off requests, approval and balances (Priority: P2)

**Goal**: Leave types, allocations (regular + accrual), multi-step approval workflow, calendar-based
duration with weekend/holiday exclusion, balance computation, overlap validation, calendar view.

**Independent Test**: quickstart.md §2 — paid leave type + 20-day allocation; 5-working-day request
spanning a weekend + holiday computes correctly; manager approval deducts balance; overlap rejected;
refuse restores; accrual ticks with cap; calendar scoping (self / team / all).

### Tests for User Story 2

- [x] T050 [P] [US2] Unit test `_leave_duration` (weekday calendar + public-holiday exclusion, day vs hour unit, zero-day → reject) in `tests/hr/test_leave_duration.py`
- [x] T051 [P] [US2] Unit test the accrual tick (`floor(periods) * rate`, `accrual_max` cap, idempotent re-run) in `tests/hr/test_leave_accrual.py`
- [x] T052 [P] [US2] Integration test each `approval_mode` (`no_validation` / `manager` / `hr` / `both`), self-approval escalation to HR Officer, `refused` from every non-terminal state, and approved→refused balance restore in `tests/hr/test_leave_approval.py`
- [x] T053 [P] [US2] Integration test balance = allocated − taken − pending, negative-balance rejection when `allow_negative=false`, and overlap rejection in `tests/hr/test_leave_balance.py`
- [ ] T054 [P] [US2] Integration test `hr.leave` record rules: employee sees own, manager sees team, Officer sees all; `leave_state_conflict` on stale approve in `tests/hr/test_access_rules.py` (extend)

### Implementation for User Story 2

- [x] T055 [P] [US2] `resource.calendar` + `resource.calendar.attendance` models in `dodoo/addons/hr/models/resource_calendar.py`
- [x] T056 [P] [US2] `hr.public.holiday` model in `dodoo/addons/hr/models/hr_public_holiday.py` (nullable `company_id`, `date_to ≥ date_from`)
- [x] T057 [P] [US2] `hr.leave.type` model in `dodoo/addons/hr/models/hr_leave_type.py` (`request_unit`, `is_paid`, `allocation_required`, `allow_negative`, `approval_mode`, nullable `company_id`)
- [x] T058 [US2] `hr.leave.allocation` model in `dodoo/addons/hr/models/hr_leave_allocation.py` (`mode` regular/accrual, accrual fields, `last_accrual_date`; `run_leave_accrual(env)` idempotent; accrual-config `create`/`write` guard) — depends on T057, T006
- [x] T059 [US2] `hr.leave` model in `dodoo/addons/hr/models/hr_leave.py`: `_leave_duration(env, employee_id, date_from, date_to, unit)` (set-based `generate_series` query, research.md D5), `create` guards (`leave_zero_days`, `leave_overlap`, `leave_insufficient_balance`), state machine, `action_approve(env, ids, uid, expected_state=None)` (approver-set resolution per ADR-025, one step, `log_transition`, `leave_state_conflict`), `action_refuse(env, ids, uid, reason, expected_state=None)`, `get_balance`, `get_duration_preview` — depends on T055–T058
- [x] T060 [US2] Export US2 models from `dodoo/addons/hr/models/__init__.py`; extend `tests/hr/test_migrations.py`
- [x] T061 [P] [US2] Add leave-type / allocation / leave / public-holiday validator models to `dodoo/addons/hr/validators.py` (contracts/hr-timeoff.md)
- [x] T062 [US2] REST routes in `dodoo/addons/hr/http/__init__.py`: `POST /hr/leave/{id}/approve`, `POST /hr/leave/{id}/refuse`, `POST /hr/cron/leave-accrual` (Administrator) — validate, resolve approver set, group-check, envelope — depends on T059, T061
- [x] T063 [US2] Append US2 `ir.rule` rows to `dodoo/addons/hr/data/rules.py` (`hr.leave` owner|manager, Officer full, deny-by-default; `hr.leave.allocation`; catalog rows for `hr.leave.type` / `hr.public.holiday` / `resource.calendar*`)
- [x] T064 [US2] Extend `dodoo/addons/hr/data/seed.py`: one `resource.calendar` per company (Mon–Fri 08–12/13–17) + attendance rows; seed ~4 leave types (Paid Time Off, Sick, Unpaid, Compensatory); empty public-holiday set; add US2 indexes (`idx_hr_leave_employee_type_state`, `idx_hr_leave_dates`, `idx_hr_leave_allocation_employee_type`, `idx_hr_public_holiday_range`) to `indexes.py`; register `sync_ir_model` entries
- [x] T065 [P] [US2] `dodoo/addons/hr/static/views/timeoff-calendar.js` — calendar view via the generic `calendar.js` (`model:"hr.leave"`, `dateStartField:"date_from"`, `dateStopField:"date_to"`, colour by `leave_type_id`), scoped query per caller role
- [x] T066 [P] [US2] `dodoo/addons/hr/static/views/timeoff-form.js` — request form with live `get_duration_preview` + Approve/Refuse buttons calling the REST routes with `expected_state`
- [x] T067 [US2] Wire `#/hr/timeoff` (calendar), `#/hr/timeoff/:id` (+ `/new`), `#/hr/allocations` routes + the Time Off menu section in `app.js`; bump `CLIENT_BUILD` — depends on T065, T066
- [x] T068 [US2] E2E `tests/e2e/test_hr_ui.py` (extend) — submit leave spanning weekend+holiday, manager approve, balance change, overlap reject, calendar scoping
- [ ] T069 [US2] Extend `tests/e2e/test_web_ui_a11y.py` with the Time Off calendar + form (keyboard day nav, status text+ARIA)

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 — Recruitment pipeline and hire conversion (Priority: P2)

**Goal**: Published jobs, Kanban pipeline over recruitment stages, applicants with source +
interviewers, refuse-with-reason, hired-stage flag, idempotent applicant→employee conversion.

**Independent Test**: quickstart.md §3 — publish a job, create applicants, move across stages
(pointer + keyboard), refuse one with a reason, move another to the hired stage and convert →
exactly one new employee linked back, second conversion is a no-op, no login user created.

### Tests for User Story 3

- [ ] T070 [P] [US3] Integration test pipeline: `get_pipeline` grouping/order, `action_set_stage` (guarded, logged, `applicant_stage_conflict`), refuse + reason leaves the active pipeline, hired-stage detection in `tests/hr/test_recruitment_pipeline.py`
- [ ] T071 [P] [US3] Integration test `create_employee` from applicant: carries name/email/phone/job/department, links `employee_id`, **no `user_id`**, idempotent second run in `tests/hr/test_recruitment_pipeline.py`
- [ ] T072 [P] [US3] Integration test recruitment validators + Officer-only REST auth in `tests/hr/test_validators.py` (extend)

### Implementation for User Story 3

- [ ] T073 [P] [US3] `hr.recruitment.stage` model in `dodoo/addons/hr/models/hr_recruitment_stage.py` (`sequence`, `is_hired_stage`, `fold`, nullable `company_id`)
- [ ] T074 [P] [US3] `hr.recruitment.source` model in `dodoo/addons/hr/models/hr_recruitment_source.py` (`is_referral`, nullable `company_id`)
- [ ] T075 [P] [US3] `hr.applicant.refuse.reason` model in `dodoo/addons/hr/models/hr_applicant_refuse_reason.py` (global)
- [ ] T076 [US3] `hr.applicant` model in `dodoo/addons/hr/models/hr_applicant.py`: fields + interviewer M2M, `department_id` default from `job_id`, `action_set_stage(env, ids, stage_id, uid, expected_stage_id=None)` (guarded, `log_transition`, `applicant_stage_conflict`), `action_refuse(env, ids, uid, reason_id)`, `create_employee(env, id, uid)` (idempotent, no `user_id`, `log_transition` event `applicant_hired`), `get_pipeline(env, job_id)` (single grouped query, PERF-003) — depends on T073–T075, T033
- [ ] T077 [US3] Export US3 models from `dodoo/addons/hr/models/__init__.py`; extend `tests/hr/test_migrations.py`
- [ ] T078 [P] [US3] Add applicant / stage / source validator models to `dodoo/addons/hr/validators.py` (contracts/hr-recruitment.md)
- [ ] T079 [US3] REST routes in `dodoo/addons/hr/http/__init__.py`: `POST /hr/applicant/{id}/set-stage`, `POST /hr/applicant/{id}/refuse`, `POST /hr/applicant/{id}/create-employee` (Officer-gated) — depends on T076, T078
- [ ] T080 [US3] Append US3 `ir.rule` rows to `dodoo/addons/hr/data/rules.py` (`hr.applicant` company-scoped for Officer+, deny-by-default; catalog rows for stage / source / refuse-reason)
- [ ] T081 [US3] Extend `dodoo/addons/hr/data/seed.py`: recruitment stages (Initial Qualification, First Interview, Second Interview, Contract Proposal, **Contract Signed** `is_hired_stage=True`), sources (LinkedIn, Website, **Employee Referral** `is_referral=True`, Agency, Other), refuse reasons; add `idx_hr_applicant_job_stage` / `_company` / `_refused` to `indexes.py`; register `sync_ir_model` entries
- [ ] T082 [P] [US3] `dodoo/addons/hr/static/views/recruitment-kanban.js` — pipeline via the generic `kanban.js` (`model:"hr.applicant"`, `groupBy:"stage_id"`, `columns` from `hr.recruitment.stage` ordered by `sequence`, `moveEndpoint:"/hr/applicant/{id}/set-stage"`, keyboard "Move to…" menu)
- [ ] T083 [P] [US3] `dodoo/addons/hr/static/views/applicant-form.js` — applicant form + interviewer picker + Refuse (reason) + Create Employee buttons
- [ ] T084 [US3] Wire `#/hr/recruitment` (job list), `#/hr/recruitment/:jobId` (Kanban), `#/hr/applicant/:id` routes + the Recruitment menu section (with a job "Publish" toggle) in `app.js`; bump `CLIENT_BUILD` — depends on T082, T083
- [ ] T085 [US3] E2E `tests/e2e/test_recruitment_ui.py` — publish job, create applicants, **stage move by pointer AND by keyboard**, refuse with reason, convert to employee (idempotent), RTL
- [ ] T086 [US3] Extend `tests/e2e/test_web_ui_a11y.py` with the Recruitment Kanban (keyboard alternative to drag, WCAG 2.1 AA)

**Checkpoint**: US1 + US2 + US3 independently functional.

---

## Phase 6: User Story 4 — Appraisal cycle with two-sided feedback (Priority: P3)

**Goal**: Templates with feedback sections + frequency; appraisal state machine
(new → pending confirmation → confirmed → done / cancelled); per-side feedback with visibility
control; next-appraisal-date computation; per-employee history.

**Independent Test**: quickstart.md §4 — launch from template, advance states, employee feedback
hidden until published, done sets next date = +12 months, history shows past appraisals, cancel
removes "open" without touching the next date.

### Tests for User Story 4

- [ ] T087 [P] [US4] Integration test appraisal state machine (legal moves, `appraisal_transition_invalid`, `appraisal_state_conflict`), `action_launch` instantiating both sides' feedback rows, `action_done` next-date resolution (employee → department → template), and manager-side routing when the appraisee is their own manager or has no manager (routes/approves via an HR Officer, per spec Edge Cases) in `tests/hr/test_appraisal_cycle.py`
- [ ] T088 [P] [US4] Integration test feedback visibility: opposite side cannot read `is_visible=false` rows via `read`/`search_read`; owning side always can; `feedback_wrong_side` on cross-side write in `tests/hr/test_appraisal_cycle.py`
- [ ] T089 [P] [US4] Integration test `hr.appraisal` record rules (owner OR manager OR Officer) and `get_history` ordering in `tests/hr/test_access_rules.py` (extend)

### Implementation for User Story 4

- [ ] T090 [P] [US4] `hr.appraisal.template` + `hr.appraisal.feedback.section` models in `dodoo/addons/hr/models/hr_appraisal_template.py` (`default_frequency_months` 1–60, ordered sections)
- [ ] T091 [P] [US4] `hr.appraisal.feedback` model in `dodoo/addons/hr/models/hr_appraisal_feedback.py` (`side`, `content`, `is_visible`; `read`/`search_read` override filtering `is_visible=false` for the opposite side; write restricted to owning side)
- [ ] T092 [US4] `hr.appraisal` model in `dodoo/addons/hr/models/hr_appraisal.py`: state machine, `action_launch(env, employee_id, template_id, uid)` (create + copy sections × 2 sides), `action_confirm` / `action_to_confirmed` / `action_done` / `action_cancel` (guarded, `log_transition`), `action_done` sets `employee.next_appraisal_date` via resolved frequency (employee → department → template), `_resolve_appraiser(employee)` returning the manager's user, or an HR Officer in the employee's company when the employee has no manager or would be their own appraiser, `get_history(env, employee_id)` — depends on T090, T091, T033, T006
- [ ] T093 [US4] Add the `appraisal_frequency_months` `Integer` field to `hr.department` in `dodoo/addons/hr/models/hr_department.py` (the `hr.employee` `appraisal_frequency_months` + `next_appraisal_date` fields are already created by T033); extend `tests/hr/test_migrations.py` to assert `hr_department.appraisal_frequency_months` exists
- [ ] T094 [US4] Export US4 models from `dodoo/addons/hr/models/__init__.py`
- [ ] T095 [P] [US4] Add appraisal template / launch / set-state / feedback validator models to `dodoo/addons/hr/validators.py` (contracts/hr-appraisal.md)
- [ ] T096 [US4] REST routes in `dodoo/addons/hr/http/__init__.py`: `POST /hr/appraisal/launch`, `POST /hr/appraisal/{id}/set-state` (Officer or manager) — depends on T092, T095
- [ ] T097 [US4] Append US4 `ir.rule` rows to `dodoo/addons/hr/data/rules.py` (`hr.appraisal` owner|manager|Officer, `hr.appraisal.feedback` via parent + visibility, deny-by-default; catalog rows for template)
- [ ] T098 [US4] Extend `dodoo/addons/hr/data/seed.py`: one `hr.appraisal.template` ("Annual Review", 12 months) with 2–3 feedback sections; add `idx_hr_appraisal_employee_state` / `_company` / `idx_hr_appraisal_feedback_appraisal` to `indexes.py`; register `sync_ir_model` entries
- [ ] T099 [P] [US4] `dodoo/addons/hr/static/views/appraisal-form.js` — state buttons, per-side feedback sections each with a visibility toggle, and (on the employee form) an appraisal-history list from `get_history`
- [ ] T100 [US4] Wire `#/hr/appraisals`, `#/hr/appraisal/:id` (+ `/new`) routes + the Appraisals menu section in `app.js`; add the history block to `employee-form.js`; bump `CLIENT_BUILD` — depends on T099
- [ ] T101 [US4] E2E `tests/e2e/test_hr_ui.py` (extend) — launch, advance, per-side visibility, done → next date, history, cancel
- [ ] T102 [US4] Extend `tests/e2e/test_web_ui_a11y.py` with the appraisal form (visibility toggles labelled, status text+ARIA)

**Checkpoint**: US1–US4 independently functional.

---

## Phase 7: User Story 5 — Employee referrals into recruitment (Priority: P3)

**Goal**: An employee refers a candidate to a published job → a linked applicant is created,
attributed to the referrer; the referrer tracks status; per-referrer total/hired counts.

**Independent Test**: quickstart.md §5 — submit a referral for a published job (blocked for
unpublished), applicant created with the referral source + back-link, status follows the pipeline,
stats show total/hired, conversion marks it hired.

**Depends on**: US3 (creates an `hr.applicant`).

### Tests for User Story 5

- [ ] T103 [P] [US5] Integration test `action_submit` (published-only → `referral_job_unpublished`, applicant created with `is_referral` source + `referral_id`, referrer resolved from current user → `referral_no_employee` when absent) in `tests/hr/test_referral.py`
- [ ] T104 [P] [US5] Integration test derived `status` transitions (stage name → `refused` → `hired`) and `get_referrer_stats` `{total, hired}`; referral to a later-unpublished job stays visible, new ones blocked in `tests/hr/test_referral.py`
- [ ] T105 [P] [US5] Integration test `hr.referral` record rule (`referrer_id.user_id = uid` for HR Employee; Officer full) in `tests/hr/test_access_rules.py` (extend)

### Implementation for User Story 5

- [ ] T106 [US5] `hr.referral` model in `dodoo/addons/hr/models/hr_referral.py`: fields, `action_submit(env, vals, uid)` (publish guard, resolve referrer via `hr.employee.resolve_current`, create linked `hr.applicant` with the `is_referral` source + `referral_id`, `log_transition` event `referral_submit`), derived `status` on read, `get_my_referrals(env)`, `get_referrer_stats(env, referrer_id)` — depends on T076 (US3), T033
- [ ] T107 [US5] Add `referral_id` Many2one to `hr.applicant` (additive) in `hr_applicant.py`; export `hr.referral` from `models/__init__.py`; extend `tests/hr/test_migrations.py`
- [ ] T108 [P] [US5] Add `ReferralSubmit` validator model to `dodoo/addons/hr/validators.py` (contracts/hr-referral.md)
- [ ] T109 [US5] REST route `POST /hr/referral/submit` in `dodoo/addons/hr/http/__init__.py` (any authenticated user with an `hr.employee`) — depends on T106, T108
- [ ] T110 [US5] Append US5 `ir.rule` rows to `dodoo/addons/hr/data/rules.py` (`hr.referral` owner / Officer / deny-by-default); add `idx_hr_referral_referrer` / `_job` to `indexes.py`; register `sync_ir_model` entry
- [ ] T111 [P] [US5] `dodoo/addons/hr/static/views/referral-form.js` — published-job picker, candidate fields, submit; a "My Referrals" list from `get_my_referrals` with live status
- [ ] T112 [US5] Wire `#/hr/referrals`, `#/hr/referral/new` routes + the Referrals menu section in `app.js`; bump `CLIENT_BUILD` — depends on T111
- [ ] T113 [US5] E2E `tests/e2e/test_recruitment_ui.py` (extend) — submit referral, advance applicant, referrer sees status + counts, unpublished-job block
- [ ] T114 [US5] Extend `tests/e2e/test_web_ui_a11y.py` with the referral form

**Checkpoint**: US1–US5 independently functional.

---

## Phase 8: User Story 6 — Fleet vehicles, drivers, contracts and alerts (Priority: P3)

**Goal**: The `fleet` addon — vehicles with a 7-state lifecycle, brands/models, employee drivers
(history retained), odometer logs, leasing/insurance contracts with expiry alerts, service logs;
Fleet Manager group.

**Independent Test**: quickstart.md §6 — brand/model → vehicle (starts `new_request`) → `registered`
→ assign employee driver → odometer logs (latest shown, lower flagged) → insurance/leasing contracts
appear in the alert list with days-left → service log recorded; non-Fleet-Manager denied.

### Tests for User Story 6

- [ ] T115 [P] [US6] Integration test vehicle state machine (`vehicle_state_conflict`), `brand_id` derived from `model_id`, driver assignment + `former_driver_ids` history, and `needs_reassignment` set when the current driver's employee is archived in `tests/fleet/test_vehicle_lifecycle.py`
- [ ] T116 [P] [US6] Integration test odometer: `_latest_odometer` (max date), a value below the prior max accepted but `inconsistent=true` + warning log in `tests/fleet/test_odometer.py`
- [ ] T117 [P] [US6] Integration test `get_expiry_alerts` window classification + `days_left`, `run_fleet_contract_expiry` idempotent flip, `expiration_date ≥ start_date` guard in `tests/fleet/test_contract_alerts.py`
- [ ] T118 [P] [US6] Integration test Fleet record rules: Fleet Manager full, HR Officer read, driver reads own vehicle, deny-by-default in `tests/fleet/test_access_rules.py`

### Implementation for User Story 6

- [ ] T119 [P] [US6] `fleet.vehicle.model.brand` + `fleet.vehicle.model` models in `dodoo/addons/fleet/models/fleet_vehicle_model.py` (brand global; model `brand_id` required)
- [ ] T120 [US6] `fleet.vehicle` model in `dodoo/addons/fleet/models/fleet_vehicle.py`: 7-state `Selection`, `action_set_state(env, ids, target, uid, expected_state=None)` (Fleet-Manager-guarded, `log_transition`, `vehicle_state_conflict`), `brand_id` derived on `create`/`write`, `driver_id` change appends prior to `former_driver_ids` (Json), `flag_reassignment_for_archived_drivers(env)` setting `needs_reassignment=True` on vehicles whose `driver_id` employee is archived (spec Edge Cases "Vehicle driver who leaves the company"; called from `run_fleet_contract_expiry` or its own `POST /fleet/cron/...` — reuse the T126 cron route), `odometer` computed from latest log, `get_assigned(env, employee_id)`, `name` derived — depends on T119, T033 (`hr.employee`), T006
- [ ] T121 [P] [US6] `fleet.vehicle.odometer` model in `dodoo/addons/fleet/models/fleet_vehicle_odometer.py` (`inconsistent` set on create when below max; `_latest_odometer`)
- [ ] T122 [US6] `fleet.vehicle.log.contract` model in `dodoo/addons/fleet/models/fleet_vehicle_log_contract.py`: `cost_type`, `amount` + `currency_id`, `state` open/expired/closed, `FLEET_ALERT_WINDOW_DAYS=30`, `get_expiry_alerts(env, window_days=None)`, `run_fleet_contract_expiry(env)` idempotent, date guard — depends on T120, T006
- [ ] T123 [P] [US6] `fleet.vehicle.log.services` model in `dodoo/addons/fleet/models/fleet_vehicle_log_services.py`
- [ ] T124 [US6] Export all fleet models from `dodoo/addons/fleet/models/__init__.py`; extend `tests/fleet/test_migrations.py`
- [ ] T125 [P] [US6] Add brand / model / vehicle / set-state / assign-driver / odometer / contract-log / service-log validator models to `dodoo/addons/fleet/validators.py` (contracts/fleet.md)
- [ ] T126 [US6] REST routes in `dodoo/addons/fleet/http/__init__.py`: `POST /fleet/vehicle/{id}/set-state`, `POST /fleet/vehicle/{id}/assign-driver`, `GET /fleet/alerts`, `POST /fleet/cron/contract-expiry` (also runs `flag_reassignment_for_archived_drivers` from T120) — depends on T120, T122, T125
- [ ] T127 [US6] `fleet` `ir.rule` rows in `dodoo/addons/fleet/data/rules.py` (Fleet Manager full, HR Officer read, driver-reads-own on `fleet.vehicle`, logs via parent, deny-by-default) + `sync_ir_model` entries; add `idx_fleet_vehicle_*`, `idx_fleet_odometer_vehicle_date`, `idx_fleet_log_contract_expiry` / `_vehicle`, `idx_fleet_log_services_vehicle` to `dodoo/addons/fleet/data/indexes.py`
- [ ] T128 [US6] Implement `seed_fleet_data(env)` in `dodoo/addons/fleet/data/seed.py`: 6 brands, 2 models each; call `groups.seed`, `sync_ir_model`, `ensure_indexes`, `rules.apply`
- [ ] T129 [P] [US6] `dodoo/addons/fleet/static/fleet-menu.js` (Vehicles / Alerts / Configuration sections, `requires:"fleet_manager"`) and `dodoo/addons/fleet/static/views/vehicle-kanban.js` (generic `kanban.js`, `groupBy:"state"`)
- [ ] T130 [P] [US6] `dodoo/addons/fleet/static/views/vehicle-form.js` (state control, driver assign, odometer history, contracts, services) and `dodoo/addons/fleet/static/views/fleet-alerts.js` (`GET /fleet/alerts` list)
- [ ] T131 [US6] Wire `#/fleet/vehicles`, `#/fleet/vehicle/:id`, `#/fleet/alerts` routes + `_renderFleetMenu` in `dodoo/addons/web/static/app.js`; bump `CLIENT_BUILD` — depends on T129, T130
- [ ] T132 [US6] E2E `tests/e2e/test_hr_ui.py` (extend) or new `tests/e2e/test_fleet_ui.py` — vehicle lifecycle, driver assign, odometer, alert list, service log; non-Fleet-Manager denied; RTL
- [ ] T133 [US6] Extend `tests/e2e/test_web_ui_a11y.py` with the Fleet screens

**Checkpoint**: all six user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T134 [P] Verify `docs/adr/024`–`027` are complete and match the as-built engines; cross-link from plan.md (Principle V)
- [ ] T135 [P] Benchmark `tests/benchmarks/test_hr_directory_perf.py` — seed 2,000 employees, assert first-page name/department/job search < 500 ms (PERF-001 / SC-009)
- [ ] T136 [P] Benchmark `tests/benchmarks/test_leave_balance_perf.py` — seed 5 years of allocations/leaves, assert `get_balance` < 300 ms (PERF-002 / SC-009)
- [ ] T137 [P] Benchmark the recruitment Kanban (`get_pipeline`, 500 applicants < 800 ms, PERF-003) and fleet alerts (5,000 contracts < 500 ms, PERF-004) in `tests/benchmarks/`
- [ ] T138 Security hardening pass: audit every REST route for `auth="session"` + `require_groups`, every custom `execute_kw` method for `validate(...)`, confirm no f-string SQL with user data, confirm no PII in any `log_transition`/`_log` `extra` (SEC-001–007, OWASP review in research.md)
- [ ] T139 [P] Observability review: grep tests for a structured JSON log line (correlation_id, actor_uid, model, record_id, from, to) on every transition type across all six areas (SC-008 / Principle IX)
- [ ] T140 [P] Accessibility audit across all HR + Fleet screens in LTR and RTL — contrast, keyboard-only Kanban move, calendar day nav, org-chart structure, status text+ARIA (SC-011 / ACC-001–004); record results in `tests/e2e/test_web_ui_a11y.py`
- [ ] T141 [P] Run `ruff check` + `black --check` over `dodoo/addons/hr`, `dodoo/addons/fleet`, `tests/hr`, `tests/fleet`; run the suite with coverage and confirm ≥ 80% unit-line coverage overall and 100% branch coverage on the contract-state table, leave duration/balance/accrual, appraisal next-date + appraiser resolution, fleet expiry classification, every from-state guard, and every whitelist validator (Principles I, II); remove dead code / unjustified comments
- [ ] T142 Run `specs/006-human-resources/quickstart.md` §0–§9 end to end on a fresh database; fix any drift; confirm the Definition-of-Done table (SC-001–SC-012) passes
- [ ] T143 [P] Update `dodoo/addons/hr/__init__.py` and `dodoo/addons/fleet/__init__.py` module docstrings to summarise the delivered scope (matching the `localization/__init__.py` precedent)
- [ ] T144 [P] Internationalise the HR + Fleet UI (FR-010, SC-011): wrap every user-facing literal in `hr/static/hr-menu.js`, `fleet/static/fleet-menu.js`, and all `hr/static/views/*.js` + `fleet/static/views/*.js` in `t(...)` (the `web/static/i18n.js` helper), and add the corresponding keys to `dodoo/addons/localization/data/i18n/en.json` and `ar.json`; verify model field labels already translate via 005's `fields_get` path. Extend `tests/e2e/test_hr_ui.py` to assert menu + button strings render in Arabic under RTL

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → no dependencies.
- **Foundational (Phase 2)** → depends on Setup; **blocks all user stories**.
- **US1 (Phase 3)** → depends on Foundational only. **MVP.**
- **US2 (Phase 4)** → depends on Foundational; uses `hr.employee` (US1) for the requester/manager but is independently testable with its own seed.
- **US3 (Phase 5)** → depends on Foundational; uses `hr.job` / `hr.department` (US1).
- **US4 (Phase 6)** → depends on Foundational; uses `hr.employee` + manager relation (US1).
- **US5 (Phase 7)** → depends on **US3** (creates an `hr.applicant`) + `hr.employee` (US1).
- **US6 (Phase 8)** → depends on Foundational + `hr.employee` (US1) for the driver link; the `fleet` addon is otherwise self-contained.
- **Polish (Phase 9)** → depends on all shipped stories.

### Within a story

Tests (written first, expected to fail) → models → services/workflow methods → REST endpoints →
`ir.rule` + seed + indexes → SPA views + routing → e2e. Model tasks marked [P] touch different
files; the aggregator tasks (`models/__init__.py`, `rules.py`, `seed.py`, `app.js`, shared test
files) are sequential within their story.

### Parallel opportunities

- Setup: T003, T004, T005 in parallel.
- Foundational: T015, T016, T017 (web views/CSS) parallel; T019, T020, T021 (fleet skeleton + migration test) parallel with the hr foundational tasks.
- Every story's test tasks (all `[P]`) run in parallel up front.
- Model tasks within a story marked `[P]` (e.g. T028–T032; T055–T057; T073–T075; T090–T091; T119/T121/T123) run in parallel.
- With staff: US2, US3, US4 can proceed in parallel once Foundational is done; US5 waits on US3; US6 waits only on US1's `hr.employee`.

---

## Parallel Example: User Story 1

```bash
# Tests first (all [P]):
Task: "Unit test contract _TRANSITIONS in tests/hr/test_contract_state.py"          # T022
Task: "Unit test skills guards in tests/hr/test_skills.py"                           # T023
Task: "Integration test employee directory in tests/hr/test_employee_directory.py"  # T024
Task: "Integration test org chart in tests/hr/test_org_chart.py"                     # T025
Task: "Integration test hr access rules in tests/hr/test_access_rules.py"            # T026
Task: "Integration test validators in tests/hr/test_validators.py"                   # T027

# Then models (all [P]):
Task: "hr.department model in dodoo/addons/hr/models/hr_department.py"               # T028
Task: "hr.job model in dodoo/addons/hr/models/hr_job.py"                             # T029
Task: "hr.employee.category model in dodoo/addons/hr/models/hr_employee_category.py" # T030
Task: "hr.contract.type model in dodoo/addons/hr/models/hr_contract_type.py"         # T031
Task: "Skill taxonomy models in dodoo/addons/hr/models/hr_skill.py"                  # T032
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & VALIDATE** with
   quickstart.md §1 + §7 (access rules) → demo the directory + contracts + skills + org chart.

### Incremental delivery

Foundation → US1 (MVP) → US2 → US3 → US4 → US5 → US6 → Polish. Each story is a deployable increment
that leaves the previous ones working. `fleet` (US6) can ship on its own cadence since it is a
separate addon.

### Parallel team strategy

After Foundational: Dev A → US1 then US4; Dev B → US2; Dev C → US3 then US5; Dev D → US6 (needs only
US1's `hr.employee`). Reconvene for Phase 9.

---

## Notes

- `[P]` = different files, no dependency on an incomplete task.
- Aggregator files (`models/__init__.py`, `data/rules.py`, `data/seed.py`, `data/indexes.py`,
  `web/static/app.js`, `hr/validators.py`, shared test modules) are appended to by many tasks —
  those tasks are **sequential** within their phase even when the surrounding model tasks are `[P]`.
- Every new REST route: `auth="session"` + explicit `require_groups`. Every custom `execute_kw`
  method: `validate(...)` its kwargs. Every state transition: `log_transition(...)` + a from-state
  precondition check (FR-067a).
- Commit after each task or logical group. Bump `CLIENT_BUILD` in `app.js` on any `static/` change.
- Stop at any checkpoint to validate the story independently.
