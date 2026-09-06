# Phase 1 Data Model: Human Resources

Field types are the `dodoo.core.fields` classes. All models are `BaseModel` subclasses; every table
gets `id`, `create_date`, `write_date` automatically. "co." = `company_id = Many2one("res.company")`.
Unless stated, `Many2one` is `ondelete RESTRICT` (framework default). Monetary amounts are
`NUMERIC(20,6)` non-negative; each monetary-bearing row also stores `currency_id =
Many2one("res.currency")` for display (defaulted to the company currency on create).

Legend for **Rules**: validation enforced in the model layer (`create`/`write` override or the
workflow method), not just the UI.

---

## Area P1 — Employees, org structure, tags

### hr.department
| Field | Type | Notes |
|-------|------|-------|
| name | Char(128) required | |
| parent_id | Many2one(hr.department) | optional; hierarchy |
| manager_id | Many2one(hr.employee) | |
| company_id | Many2one(res.company) required | |
| active | Boolean default True | archive flag |
| complete_name | Char(256) readonly | derived "Parent / Child" (computed on read) |
| appraisal_frequency_months | Integer | optional department-level override (resolved after the employee override, before the template default — ADR-026) |

**Rules**: reject `parent_id` that introduces a cycle (walk parents; `DodooError("department_cycle")`).
**Indexes**: `idx_hr_department_company (company_id)`, `idx_hr_department_parent (parent_id)`.

### hr.job
| Field | Type | Notes |
|-------|------|-------|
| name | Char(128) required | job title |
| department_id | Many2one(hr.department) | |
| company_id | Many2one(res.company) required | |
| expected_employees | Integer default 0 | target headcount |
| no_of_employees | Integer readonly | derived = count active hr.employee with this job_id |
| is_published | Boolean default False | recruitment/referral target flag (FR-032) |
| active | Boolean default True | |

**Rules**: `no_of_employees` computed on read (`SELECT count(*) … WHERE job_id=:id AND active`).
Over-target allowed (reported, not blocked).
**Indexes**: `idx_hr_job_company (company_id)`, `idx_hr_job_published (is_published)`.

### hr.employee
Grouped per FR-001. One table; groups are UI tabs.

| Group | Field | Type | Notes |
|-------|-------|------|-------|
| — | name | Char(256) required | |
| — | company_id | Many2one(res.company) required | |
| — | active | Boolean default True | |
| Work | work_email | Char(256) | |
| Work | work_phone | Char(64) | |
| Work | department_id | Many2one(hr.department) | |
| Work | job_id | Many2one(hr.job) | |
| Work | job_title | Char(128) | free text (may differ from job_id.name) |
| Work | work_location | Char(128) | |
| Work | manager_id | Many2one(hr.employee) | |
| Work | coach_id | Many2one(hr.employee) | |
| Personal | photo | Text | base64 data URI (nullable) |
| Personal | gender | Selection(male,female,other) | |
| Personal | birthday | Date | |
| Personal | marital | Selection(single,married,cohabitant,widower,divorced) | |
| Personal | private_email | Char(256) | |
| Personal | private_phone | Char(64) | |
| Personal | emergency_contact | Char(128) | |
| Personal | emergency_phone | Char(64) | |
| Private | country_id | Many2one(res.country) | nationality |
| Private | identification_id | Char(64) | **sensitive** |
| Private | bank_account | Char(64) | **sensitive** |
| Private | home_address | Text | **sensitive** |
| Private | dependant_count | Integer default 0 | |
| HR Settings | user_id | Many2one(res.users) | 0..1 per company (FR-005) |
| HR Settings | category_ids | Many2many(hr.employee.category, `hr_employee_category_rel`, `employee_id`, `category_id`) | tags |
| HR Settings | next_appraisal_date | Date | set by ADR-026 |
| HR Settings | appraisal_frequency_months | Integer | optional per-employee override |

**Sensitive fields** (dropped by `hr.employee.read` for non-owner, non-Officer callers — D4):
`identification_id`, `bank_account`, `home_address`, `birthday`, `marital`, `private_email`,
`private_phone`, `emergency_contact`, `emergency_phone`, `dependant_count`.
**Rules**:
- `manager_id` cycle rejected (`employee_cycle`).
- `user_id` unique per `(user_id, company_id)` — reject a second employee linking the same user in
  the same company (`user_already_linked`).
- Setting `job_id` / `active` recomputes `hr.job.no_of_employees` on read (no stored counter).
**Indexes**: `idx_hr_employee_company_name (company_id, name)`,
`idx_hr_employee_name_pattern (name text_pattern_ops)`,
`idx_hr_employee_department (department_id)`, `idx_hr_employee_job (job_id)`,
`idx_hr_employee_manager (manager_id)`, `uq_hr_employee_user_company (user_id, company_id) WHERE user_id IS NOT NULL`.

### hr.employee.category
| Field | Type | Notes |
|-------|------|-------|
| name | Char(64) required | tag label |
| color | Integer default 0 | |

Global (no `company_id`) — Odoo `hr.employee.category` is global.

---

## Area P1 — Contracts (ADR-024)

### hr.contract.type
| name Char(64) required | sequence Integer default 10 | company_id Many2one(res.company) nullable |

Nullable `company_id` (NULL = shared) per FR-064a. Seeded: Permanent, Fixed-term, Internship,
Part-time.

### hr.contract
| Field | Type | Notes |
|-------|------|-------|
| name | Char(128) required | reference |
| employee_id | Many2one(hr.employee) required | |
| company_id | Many2one(res.company) required | |
| contract_type_id | Many2one(hr.contract.type) | |
| wage | Monetary | + currency_id |
| date_start | Date required | |
| date_end | Date | optional |
| trial_date_end | Date | optional |
| state | Selection(draft,running,expired,cancelled) default draft | stored (ADR-024) |
| notes | Text | |

**State transitions** (`_TRANSITIONS`): `draft→{running,cancelled}`, `running→{expired,cancelled}`,
`{expired,cancelled}→draft`.
**Rules**:
- `date_end` ≥ `date_start` (`contract_dates`).
- `trial_date_end` within `[date_start, date_end or +∞)` (`contract_trial`).
- On `→running`: reject if the employee already has another `running` contract (`contract_running_exists`).
- `action_set_state` rejects an illegal or stale transition (`contract_state_conflict`, FR-067a) and
  logs `{event:"contract_state", from, to}`.
- `_effective_state()` (used by read/list/search): a `running` row with `date_end < today` reports
  `expired`; `run_contract_expiry(env)` persists that flip (idempotent — only touches
  `state='running' AND date_end < today`).
**Lookup**: `get_running_contract(env, employee_id)` → the `running` row whose
`[date_start, date_end]` contains today, else the latest `running` row.
**Indexes**: `idx_hr_contract_employee_state (employee_id, state)`, `idx_hr_contract_company (company_id)`,
`idx_hr_contract_date_end (date_end) WHERE state='running'`.

---

## Area P1 — Skills

### hr.skill.type
| name Char(64) required | active Boolean default True | — global |

### hr.skill
| name Char(64) required | skill_type_id Many2one(hr.skill.type) required | sequence Integer |

### hr.skill.level
| name Char(64) required | skill_type_id Many2one(hr.skill.type) required | level_progress Integer (0–100) | sequence Integer |

**Rules**: `level_progress` in `[0,100]`.

### hr.employee.skill
| employee_id Many2one(hr.employee) required | skill_id Many2one(hr.skill) required | skill_level_id Many2one(hr.skill.level) required | skill_type_id Many2one(hr.skill.type) required (denormalised for grouping) |

**Rules**:
- `skill_level_id.skill_type_id == skill_id.skill_type_id` (`skill_level_mismatch`).
- unique `(employee_id, skill_id)` (`skill_duplicate`).
**Indexes**: `uq_hr_employee_skill (employee_id, skill_id)`, `idx_hr_employee_skill_employee (employee_id)`.

---

## Area P2 — Working time & public holidays

### resource.calendar
| name Char(64) required | company_id Many2one(res.company) required | hours_per_day Float default 8 | tz Char(32) default 'UTC' |

### resource.calendar.attendance
| calendar_id Many2one(resource.calendar) required | dayofweek Selection('0'..'6') required | hour_from Float required | hour_to Float required |

One calendar seeded per company (Mon–Fri, 08:00–12:00 / 13:00–17:00).

### hr.public.holiday
| name Char(64) required | date_from Date required | date_to Date required | company_id Many2one(res.company) nullable |

Nullable `company_id` (NULL = global). Seeded empty; configured by HR Administrator.
**Rules**: `date_to ≥ date_from`.
**Indexes**: `idx_hr_public_holiday_range (date_from, date_to)`.

---

## Area P2 — Time Off (ADR-025)

### hr.leave.type
| Field | Type | Notes |
|-------|------|-------|
| name | Char(64) required | |
| company_id | Many2one(res.company) nullable | NULL = shared |
| request_unit | Selection(day,hour) default day | |
| is_paid | Boolean default True | |
| allocation_required | Boolean default True | must have allocation before requesting |
| allow_negative | Boolean default False | |
| approval_mode | Selection(no_validation,manager,hr,both) default manager | |
| color | Integer default 0 | calendar colour |

### hr.leave.allocation
| Field | Type | Notes |
|-------|------|-------|
| employee_id | Many2one(hr.employee) required | |
| leave_type_id | Many2one(hr.leave.type) required | |
| company_id | Many2one(res.company) required | |
| mode | Selection(regular,accrual) default regular | |
| number_of_units | Float default 0 | current entitlement (days or hours per type) |
| accrual_rate | Float default 0 | accrual only |
| accrual_period | Selection(day,week,month) | accrual only |
| accrual_max | Float | accrual only; 0/NULL = uncapped |
| date_from | Date | validity start (accrual anchor) |
| date_to | Date | validity end |
| last_accrual_date | Date | idempotency key for run_leave_accrual |
| state | Selection(draft,confirmed,refused) default confirmed | officer-granted → confirmed |

**Rules**: accrual fields required when `mode='accrual'`. `run_leave_accrual` adds
`floor(periods between last_accrual_date and today) * accrual_rate` to `number_of_units`, capped at
`accrual_max`, then sets `last_accrual_date` (idempotent).
**Indexes**: `idx_hr_leave_allocation_employee_type (employee_id, leave_type_id)`.

### hr.leave
| Field | Type | Notes |
|-------|------|-------|
| employee_id | Many2one(hr.employee) required | |
| leave_type_id | Many2one(hr.leave.type) required | |
| company_id | Many2one(res.company) required | |
| date_from | Datetime required | |
| date_to | Datetime required | |
| number_of_units | Float readonly | computed duration in the type's unit |
| state | Selection(to_approve,second_approval,approved,refused) default to_approve | |
| first_approver_id | Many2one(res.users) | set on step 1 |
| second_approver_id | Many2one(res.users) | set on step 2 (mode `both`) |
| refuse_reason | Char(256) | |

**State machine**: `to_approve → approved` (modes `no_validation` auto, `manager`, `hr`);
`to_approve → second_approval → approved` (mode `both`); `→ refused` from `to_approve`,
`second_approval`, `approved`.
**Rules** (all in the workflow methods / `create`):
- Duration = `_leave_duration(...)`; reject if 0 after calendar + holiday exclusion (`leave_zero_days`).
- Overlap: reject if any non-`refused` `hr.leave` for the same employee overlaps `[date_from,date_to]`
  (`leave_overlap`).
- Balance: if `leave_type.allocation_required` and not `allow_negative`, reject when
  `allocated − taken − pending < number_of_units` (`leave_insufficient_balance`).
- `action_approve(env, ids, uid)`: resolve approver set (ADR-025); reject if `uid` not permitted or
  is the requester with no other approver (`leave_self_approval` → escalates); advance one step;
  log `{event:"leave_approve", from, to}`. Stale state → `leave_state_conflict` (FR-067a).
- `action_refuse(env, ids, uid, reason)`: `→ refused`; if previous state was `approved`, balance is
  naturally restored (taken recomputed). Log.
- Balance consumed = SUM(`number_of_units`) of `approved` leaves (no stored counter).
**Indexes**: `idx_hr_leave_employee_type_state (employee_id, leave_type_id, state)`,
`idx_hr_leave_dates (date_from, date_to)`, `idx_hr_leave_company (company_id)`.

---

## Area P2 — Recruitment

### hr.recruitment.stage
| name Char(64) required | sequence Integer default 10 | is_hired_stage Boolean default False | company_id Many2one(res.company) nullable | fold Boolean default False |

Seeded: Initial Qualification, First Interview, Second Interview, Contract Proposal,
Contract Signed *(is_hired_stage=True)*.

### hr.recruitment.source
| name Char(64) required | is_referral Boolean default False | company_id Many2one nullable |

Seeded: LinkedIn, Website, Employee Referral *(is_referral=True)*, Agency, Other.

### hr.applicant
| Field | Type | Notes |
|-------|------|-------|
| partner_name | Char(128) required | candidate name |
| email_from | Char(256) | |
| partner_phone | Char(64) | |
| job_id | Many2one(hr.job) required | |
| department_id | Many2one(hr.department) | defaulted from job_id.department_id, overridable |
| company_id | Many2one(res.company) required | |
| source_id | Many2one(hr.recruitment.source) | |
| stage_id | Many2one(hr.recruitment.stage) required | defaulted to lowest `sequence` |
| interviewer_ids | Many2many(res.users, `hr_applicant_interviewer_rel`, `applicant_id`, `user_id`) | |
| refused | Boolean default False | |
| refuse_reason_id | Many2one(hr.applicant.refuse.reason) | |
| employee_id | Many2one(hr.employee) | set by create_employee |
| referral_id | Many2one(hr.referral) | back-link when created from a referral |

**Rules / methods**:
- `action_set_stage(env, ids, stage_id, uid)`: guarded (must be recruiter/Officer for the company);
  logs `{event:"applicant_stage", from, to}`. `refused` rows are excluded from the pipeline query.
- `action_refuse(env, ids, uid, reason_id)`: `refused=True`; keeps data; logs.
- `create_employee(env, id, uid)`: idempotent — if `employee_id` set, returns it; else creates
  `hr.employee` with `name=partner_name`, `work_email=email_from`, `work_phone=partner_phone`,
  `job_id`, `department_id`, `company_id`; sets `applicant.employee_id`; **no `user_id`** (clarify
  pass 2); logs `{event:"applicant_hired", employee_id}`.
- "hired" = `stage_id.is_hired_stage`.
**Indexes**: `idx_hr_applicant_job_stage (job_id, stage_id)`, `idx_hr_applicant_company (company_id)`,
`idx_hr_applicant_refused (refused)`.

### hr.applicant.refuse.reason
| name Char(128) required | — global |
Seeded: Not enough experience, Salary expectations, Position filled, Withdrew, Other.

---

## Area P3 — Appraisals (ADR-026)

### hr.appraisal.template
| name Char(64) required | default_frequency_months Integer default 12 | company_id Many2one nullable |

### hr.appraisal.feedback.section
| template_id Many2one(hr.appraisal.template) required | title Char(128) required | prompt Text | sequence Integer default 10 |

### hr.appraisal
| Field | Type | Notes |
|-------|------|-------|
| employee_id | Many2one(hr.employee) required | appraisee |
| manager_id | Many2one(hr.employee) | appraiser; defaults to employee_id.manager_id |
| company_id | Many2one(res.company) required | |
| template_id | Many2one(hr.appraisal.template) | |
| state | Selection(new,pending_confirmation,confirmed,done,cancelled) default new | |
| date_close | Date | set on `→done` |
| frequency_months | Integer | resolved snapshot (employee→department→template) |

**State machine**: `new → pending_confirmation → confirmed → done`; `* → cancelled` from any
non-`done`.
**Methods**:
- `action_launch(env, employee_id, template_id, uid)`: create appraisal (`new`) + copy each
  template section into two `hr.appraisal.feedback` rows (`side='employee'`, `side='manager'`).
- `action_confirm` / `action_to_confirmed` / `action_done` / `action_cancel`: each guarded
  (FR-067a → `appraisal_state_conflict`), logged.
- `action_done`: `date_close = today`; `employee.next_appraisal_date = today + frequency_months`
  (frequency resolved employee → department → template).
- History: `search([['employee_id','=',id]], order='date_close desc, id desc')`; open = single
  non-`done`/`cancelled` row.
**Indexes**: `idx_hr_appraisal_employee_state (employee_id, state)`, `idx_hr_appraisal_company (company_id)`.

### hr.appraisal.feedback
| appraisal_id Many2one(hr.appraisal) required | side Selection(employee,manager) required | section_title Char(128) | content Text | is_visible Boolean default False |

**Rules**: `hr.appraisal.feedback.read` / `search_read` for a caller who is the *opposite* side
filters out `is_visible=False` rows (model layer, FR-042). The owning side always sees its own rows.
**Indexes**: `idx_hr_appraisal_feedback_appraisal (appraisal_id)`.

---

## Area P3 — Referrals

### hr.referral
| Field | Type | Notes |
|-------|------|-------|
| referrer_id | Many2one(hr.employee) required | |
| job_id | Many2one(hr.job) required | must be `is_published` |
| company_id | Many2one(res.company) required | |
| candidate_name | Char(128) required | |
| candidate_email | Char(256) | |
| candidate_phone | Char(64) | |
| applicant_id | Many2one(hr.applicant) | created by action_submit |
| status | Char(64) readonly | derived = `applicant_id.stage_id.name`, or `refused`, or `hired` |

**Methods**:
- `action_submit(env, vals, uid)`: reject if `job_id` not `is_published` (`referral_job_unpublished`);
  create `hr.applicant` with `source_id` = the `is_referral` source, `referral_id` set; store
  `applicant_id`; log.
- Counts: `get_referrer_stats(env, referrer_id)` → `{total, hired}` where `hired` counts referrals
  whose `applicant_id.employee_id IS NOT NULL`.
- A job later un-published: existing referrals keep working; `action_submit` blocked.
**Indexes**: `idx_hr_referral_referrer (referrer_id)`, `idx_hr_referral_job (job_id)`.

---

## Area P3 — Fleet (ADR-027) — addon `dodoo/addons/fleet/`

### fleet.vehicle.model.brand
| name Char(64) required | — global | Seeded: Toyota, Volkswagen, Ford, BMW, Renault, Hyundai. |

### fleet.vehicle.model
| name Char(64) required | brand_id Many2one(fleet.vehicle.model.brand) required | Seeded: 2 per brand. |

### fleet.vehicle
| Field | Type | Notes |
|-------|------|-------|
| name | Char(128) readonly | derived "Brand Model / plate" |
| model_id | Many2one(fleet.vehicle.model) required | |
| brand_id | Many2one(fleet.vehicle.model.brand) | derived from model_id on create/write |
| license_plate | Char(32) | |
| company_id | Many2one(res.company) required | |
| state | Selection(new_request,to_order,ordered,registered,downgraded,reserved,waiting_list) default new_request | |
| driver_id | Many2one(hr.employee) | current driver |
| former_driver_ids | Json | list of prior `hr.employee` ids (history, FR-054) |
| odometer | Float readonly | derived = latest odometer log value |
| needs_reassignment | Boolean default False | set when driver's employee is archived |

**Methods**: `action_set_state(env, ids, target, uid)` guarded (Fleet Manager), logged
(`fleet_vehicle_state`, FR-067a → `vehicle_state_conflict`). On `driver_id` change, the prior value
is appended to `former_driver_ids`.
**Indexes**: `idx_fleet_vehicle_company (company_id)`, `idx_fleet_vehicle_driver (driver_id)`,
`idx_fleet_vehicle_state (state)`.

### fleet.vehicle.odometer
| vehicle_id Many2one(fleet.vehicle) required | value Float required | date Date required | inconsistent Boolean default False |

**Rules**: on create, if `value < ` current max for the vehicle → `inconsistent=True` (accepted),
log `warning`. `_latest_odometer(vehicle_id)` = row with `max(date)` (tie → max `id`).
**Indexes**: `idx_fleet_odometer_vehicle_date (vehicle_id, date DESC)`.

### fleet.vehicle.log.contract
| Field | Type | Notes |
|-------|------|-------|
| vehicle_id | Many2one(fleet.vehicle) required | |
| cost_type | Selection(leasing,insurance) required | |
| amount | Monetary | + currency_id |
| start_date | Date required | |
| expiration_date | Date required | |
| state | Selection(open,expired,closed) default open | stored (ADR-027) |
| notes | Text | |

**Methods**: `get_expiry_alerts(env, window_days=FLEET_ALERT_WINDOW_DAYS)` → rows where
`expiration_date <= today + window` OR `state='expired'`, each `{contract, vehicle, days_left =
expiration_date - today}`. `run_fleet_contract_expiry(env)` flips `open → expired` past the date
(idempotent).
**Rules**: `expiration_date ≥ start_date`.
**Indexes**: `idx_fleet_log_contract_expiry (expiration_date)`, `idx_fleet_log_contract_vehicle (vehicle_id)`.

### fleet.vehicle.log.services
| vehicle_id Many2one(fleet.vehicle) required | service_type Char(64) required | date Date required | amount Monetary + currency_id | notes Text |
**Indexes**: `idx_fleet_log_services_vehicle (vehicle_id)`.

---

## Security groups & record rules (seeded)

`res.groups` rows (idempotent by `name`): `HR Employee`, `HR Officer`, `HR Administrator`,
`Fleet Manager`. Nesting (`HR Employee ⊂ HR Officer ⊂ HR Administrator`) is materialised at
assignment: `assign_hr_group(env, uid, "officer")` inserts rows for `HR Employee` + `HR Officer`.

`ir.model` rows for every `hr.*` and `fleet.*` model are inserted by `data/ir_model_sync.py`
(`INSERT … ON CONFLICT (name) DO NOTHING`) so `ir.rule.model_id` resolves.

`ir.rule` rows (`domain_filter` = JSON, bound to groups) — exact domains in
`contracts/security-groups.md`. Summary:

| Model | HR Employee (owner) | HR Officer / Administrator | Deny-by-default (no group) |
|-------|--------------------|---------------------------|----------------------------|
| hr.employee | company-scoped read; sensitive fields dropped in `read` unless `user_id=uid` | company-scoped full | `[["id","=",0]]` |
| hr.contract | `[["employee_id.user_id","=",uid]]` read | company-scoped full | deny |
| hr.leave | `["|",["employee_id.user_id","=",uid],["employee_id.manager_id.user_id","=",uid]]` | company-scoped full | deny |
| hr.appraisal | same shape as hr.leave (owner OR manager) | company-scoped full | deny |
| hr.appraisal.feedback | via appraisal + `is_visible` filter for opposite side | company-scoped full | deny |
| hr.referral | `[["referrer_id.user_id","=",uid]]` | company-scoped full | deny |
| fleet.vehicle | `[["driver_id.user_id","=",uid]]` read (driver) | Officer read; Fleet Manager full | deny |
| fleet.* logs | via vehicle | Fleet Manager full | deny |
| config catalogs (leave type, stage, source, contract type, skill*, brand, model, refuse reason, holiday, calendar) | read where `company_id IS NULL OR company_id IN allowed` | Administrator / Fleet Manager write | read-only |

Every non-catalog rule additionally ANDs `["company_id","in", <allowed>]` (FR-064). Menu entries in
`hr-menu.js` / `fleet-menu.js` are filtered client-side by the caller's group flags returned from
`/web/core/info`; server enforcement is the record rules + REST action group checks (defence in
depth, SEC-004).

## Entity relationship summary

```
res.company 1─* hr.department ─* hr.job ─* hr.employee ─* hr.contract
                                   │            │  │ └─* hr.employee.skill ─ hr.skill ─ hr.skill.type ─* hr.skill.level
                                   │            │  └─ res.users (0..1)
                                   │            └─* hr.appraisal ─* hr.appraisal.feedback   hr.appraisal.template ─* section
                                   │
hr.job ─* hr.applicant ─ hr.recruitment.stage / .source / .refuse.reason ; hr.applicant 0..1─ hr.employee
hr.employee ─* hr.referral ─ hr.job(published) ─ hr.applicant(1)
hr.employee ─* hr.leave / hr.leave.allocation ─ hr.leave.type ; resource.calendar ─* attendance ; hr.public.holiday
fleet.vehicle.model.brand ─* fleet.vehicle.model ─* fleet.vehicle ─ hr.employee(driver)
fleet.vehicle ─* fleet.vehicle.odometer / .log.contract / .log.services
```
