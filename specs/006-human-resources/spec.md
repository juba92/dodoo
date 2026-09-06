# Feature Specification: Human Resources

**Feature Branch**: `006-human-resources`

**Created**: 2026-09-06

**Status**: Draft

**Input**: User description: "Add a Human Resources module to dodoo that reproduces the Odoo 19.0 'Human Resources' application section — Employees, Recruitment, Time Off, Appraisals, Referrals, and Fleet — built as one or more dodoo addons (dodoo/addons/hr/, plus dodoo/addons/fleet/) following the existing architecture, and modelled on the Odoo 19.0 hr, hr_contract, hr_skills, hr_org_chart, hr_holidays, hr_recruitment, hr_appraisal, hr_referral, and fleet addons."

## Clarifications

### Session 2026-09-06

*(Resolved autonomously per the project's Speckit Automation Rules — priority order: constitution → dodoo architecture → Odoo 19.0 → minimal scope.)*

- Q: Are the configuration catalogs (leave types, skill taxonomy, recruitment stages, contract types, refusal reasons, vehicle brands/models, employee tags) shared across companies or company-specific? → A: Each catalog record carries an **optional `company_id`**; `NULL` means shared/global, a set value means company-scoped and only visible in that company. Per Odoo 19.0: skill type/skill/level, employee categories, applicant refusal reasons, and vehicle brands/models are global (no `company_id`); leave types, recruitment stages, and contract types carry a nullable `company_id`.
- Q: Does the HR addon depend on the 003-accounting (`account`) addon? → A: **No.** `hr` depends on `base` + `web` + `localization` (005); `fleet` depends on `hr`. Wage and fleet contract/service amounts are monetary values in the company currency (`res.currency`, already provided by base/005) with **no** journal entries, vendor bills, or accounting posting. This keeps the branch a clean diff on `master` after 005 without pulling in 003.
- Q: Are the new presentations (card/Kanban, calendar, org chart) generic reusable view types or HR-specific screens? → A: **Kanban and Calendar are added to the web client as generic, metadata-driven view types** reusable by any model (extending the 002-web-ui view architecture); the **org chart is a bespoke HR form widget** on the employee form, mirroring Odoo's `hr_org_chart` (a widget, not a view type). The employee "card view" is the generic Kanban view type applied to `hr.employee`.
- Q: How are concurrent/stale workflow transitions handled? → A: Every state transition performs a **server-side from-state precondition check**: if the record is no longer in the expected source state, the transition is rejected with a conflict error and logged (per FR-066), with no side effects. No new client-side version token is introduced; plain form field edits keep the 002-web-ui save semantics.
- Q: Is a login user auto-created when an employee is added or an applicant is converted? → A: **No auto-provisioning.** The employee ↔ `res.users` link is set explicitly by an HR Officer or HR Administrator. Applicant-to-employee conversion (FR-038) carries name, contact, job, and department but never creates a user.
- Q: How is HR navigation surfaced in the web client? → A: **Six addon-provided application menus** — Employees, Recruitment, Time Off, Appraisals, Referrals, Fleet — each with its own sub-menus, following the pattern the `account` addon already uses (`account-menu.js`). The generic metadata-driven model sidebar from 002 remains available (primarily for administrators); HR does not replace it.
- Q: How is an applicant's "hired" outcome modelled? → A: A boolean **hired-stage flag on Recruitment Stage** (per Odoo 19.0 `hr.recruitment.stage.hired_stage`). An applicant sitting in a hired-flagged stage is "hired" and eligible for the FR-038 conversion; "refused" stays a separate flag (FR-037). There is no additional per-applicant state machine beyond `stage` + `refused`.
- Q: Who is the approver when the employee's manager has no linked user (or there is no manager)? → A: The approving **actor is a `res.users`**: the user linked to the employee's manager employee; if there is no manager, or the manager has no linked user, approval falls to **any HR Officer in the same company scope**. A requester is never the sole approver of their own request (escalates, per the existing edge case).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Employee directory, org structure, contracts and skills (Priority: P1)

An HR officer builds and maintains the company's people records. They create departments in a
hierarchy, define job positions with a target headcount, and register employees with their personal,
work, private, and HR-settings details. Each employee can be linked to a login user, given a manager
and a coach, and tagged with categories. The officer can browse employees as cards or as a list,
open an employee form, and view an org chart that shows an employee's management chain and direct
reports. For each employee the officer records one or more contracts (wage, contract type, start/end
dates, optional trial-period end) and tracks each contract through draft → running → expired →
cancelled. The officer also records the employee's skills, each with a skill type and a level.

**Why this priority**: The employee record is the anchor every other HR area points at — time off,
recruitment conversion, appraisals, referrals, and fleet drivers all reference an employee. Without
the directory, departments, jobs, contracts, and skills there is no HR module. It delivers
standalone value: a working company directory and contract register on a fresh install.

**Independent Test**: On a fresh install, create a department tree, a job position with an expected
headcount, and three employees (one linked to a user, one with a manager, one with a coach and
tags). Confirm the directory card and list views show them, the employee form exposes the personal /
work / private / HR-settings tabs, and the org chart renders the manager chain and direct reports.
Add a contract to one employee, move it draft → running, and confirm it appears as that employee's
running contract. Add two skills to an employee and confirm they show on the employee form.

**Acceptance Scenarios**:

1. **Given** an HR officer on the Employees screen, **When** they create an employee with a name,
   work email, department, and job position, **Then** the employee is saved, appears in the card and
   list views, and the job position's current headcount increases by one.
2. **Given** a department with a parent department, **When** the officer opens the department,
   **Then** the parent and the child departments are shown and the hierarchy is navigable.
3. **Given** an employee with a manager assigned, **When** the officer opens the org chart for that
   employee, **Then** the employee's manager chain upward and their direct reports downward are
   displayed.
4. **Given** an employee linked to a login user, **When** that user signs in, **Then** the system
   can resolve "the employee record of the current user" for use by other HR areas.
5. **Given** an employee with a draft contract, **When** the officer sets it to running with a wage,
   contract type, and start date, **Then** the contract state becomes running and it is returned as
   the employee's current running contract.
6. **Given** a running contract whose end date has passed, **When** the contract list is viewed,
   **Then** that contract is shown as expired.
7. **Given** an employee form, **When** the officer adds a skill of a given skill type and picks a
   level defined for that type, **Then** the skill and its level are saved and displayed on the
   employee's skills section, and a level from a different skill type cannot be selected.
8. **Given** two companies, **When** an officer scoped to company A lists employees, **Then** only
   company A's employees, departments, and jobs are shown.
9. **Given** the active language is Arabic, **When** the Employees screens are displayed, **Then**
   labels are translated and the layout is right-to-left.

---

### User Story 2 - Time Off requests, approval and balances (Priority: P2)

An employee checks their leave balance and submits a time-off request for a date range against a
leave type. The request runs through the leave type's configured approval workflow — no approval,
single approval by their manager or the HR officer, or a second approval — reaching approved or
refused. Approved paid leave reduces the employee's balance for that leave type. HR officers grant
allocations (a fixed number of days/hours, or an accrual that adds entitlement over time). The
system rejects a request that overlaps another of the employee's leaves and accounts for weekends
and public holidays when computing the leave duration. Anyone can view time off on a calendar.

**Why this priority**: Time off is the highest-frequency HR transaction and the one employees touch
directly. It depends on the employee record (US1) for the requester, their manager, and company
scope, but nothing else, so it can ship right after the directory.

**Independent Test**: Create a paid leave type (unit = days, single manager approval) and allocate
20 days to an employee. Submit a 5-working-day request spanning a weekend and a public holiday;
confirm the duration is computed excluding the weekend and holiday. Approve it as the manager;
confirm the balance drops by the computed duration. Submit an overlapping request; confirm it is
rejected. Open the calendar and confirm the approved leave appears.

**Acceptance Scenarios**:

1. **Given** a leave type configured for single manager approval and an employee with sufficient
   allocation, **When** the employee submits a request and the manager approves it, **Then** the
   request state goes to-approve → approved and the employee's balance for that type decreases by
   the request duration.
2. **Given** a leave type configured for a second approval, **When** the first approver approves,
   **Then** the request moves to the second-approval state and is not deducted from the balance
   until the second approver approves.
3. **Given** a pending or approved request, **When** an approver refuses it, **Then** the state
   becomes refused and no balance is consumed (an approved-then-refused request restores the
   balance).
4. **Given** an employee with an approved leave on given dates, **When** they submit another request
   overlapping those dates, **Then** the new request is rejected with a clear message.
5. **Given** a leave type whose unit is days, **When** a request spans a weekend and a configured
   public holiday, **Then** the counted duration excludes the weekend days and the public holiday.
6. **Given** a leave type whose unit is hours, **When** a half-day request is submitted, **Then**
   the duration is expressed in hours against the working calendar.
7. **Given** an accrual allocation, **When** an accrual period elapses, **Then** the allocated
   amount increases by the accrual rate up to any configured cap.
8. **Given** an employee requests more than their available balance for a type that does not allow
   negative balances, **When** they submit, **Then** the request is rejected.
9. **Given** a manager, **When** they open the time-off calendar, **Then** they see their own leaves
   and the leaves of their team; a plain employee sees only their own.

---

### User Story 3 - Recruitment pipeline and hire conversion (Priority: P2)

A recruiter publishes a job position and manages applicants through a Kanban pipeline whose columns
are recruitment stages. Each applicant records a candidate name, contact details, the job applied
for, a recruitment source, and assigned interviewers. Applicants are dragged between stages; a
rejected applicant is marked refused with a refusal reason. When an applicant is hired, the
recruiter converts them into an employee, carrying over the name, contact details, job position, and
department, and links the applicant to the new employee.

**Why this priority**: Recruitment feeds the employee directory and is a prerequisite for Referrals
(US5). It depends only on jobs and departments from US1.

**Independent Test**: Publish a job position. Create an applicant for it via a source, assign an
interviewer, and move it across three stages in the Kanban. Refuse a second applicant with a reason
and confirm it leaves the active pipeline. Convert the first applicant to an employee and confirm a
new employee exists with the carried-over data and a link back to the applicant.

**Acceptance Scenarios**:

1. **Given** a job position, **When** the recruiter sets it to published, **Then** it is flagged as
   published and available as a referral target (US5).
2. **Given** a set of recruitment stages, **When** the recruiter opens the recruitment pipeline for
   a job, **Then** applicants are shown as cards grouped into columns by stage, ordered by stage
   sequence.
3. **Given** an applicant card, **When** the recruiter moves it to another stage, **Then** the
   applicant's stage updates and the change is recorded.
4. **Given** an applicant, **When** the recruiter assigns one or more interviewers, **Then** those
   users are recorded as interviewers on the applicant.
5. **Given** an applicant, **When** the recruiter marks it refused and selects a refusal reason,
   **Then** the applicant is flagged refused, leaves the active pipeline, and retains the reason.
6. **Given** an applicant in a stage flagged as a hired stage, **When** the recruiter runs "create
   employee", **Then** a new employee is created with the applicant's name, contact details, job
   position, and department, and the applicant references that employee; running it again does not
   create a second employee.

---

### User Story 4 - Appraisal cycle with two-sided feedback (Priority: P3)

An HR officer or manager launches an appraisal for an employee from a template. The appraisal moves
through new → pending confirmation → confirmed → done (or cancelled). The template provides feedback
sections; the employee fills their self-assessment and the manager fills their assessment, each side
controlling whether its feedback is published/visible to the other. The next appraisal date for an
employee is computed from a configurable frequency (e.g. every 6 or 12 months). Each employee's form
shows their appraisal history.

**Why this priority**: Appraisals are periodic and valuable but not required for day-to-day
operations. Depends on the employee record and the manager relationship from US1.

**Independent Test**: Define an appraisal template with two feedback sections and a 12-month
frequency. Launch an appraisal for an employee, confirm it, enter employee feedback unpublished and
manager feedback published, and verify each side sees only what the other has published. Mark it
done and confirm the employee's next appraisal date is 12 months later and the appraisal appears in
the employee's history.

**Acceptance Scenarios**:

1. **Given** an appraisal template and an employee, **When** the officer launches an appraisal,
   **Then** an appraisal is created in the new state with the template's feedback sections.
2. **Given** an appraisal in new, **When** it is confirmed, **Then** it moves new → pending
   confirmation → confirmed following the workflow and each transition is recorded.
3. **Given** a confirmed appraisal, **When** the employee saves self-feedback with visibility off,
   **Then** the manager cannot see that text until the employee turns visibility on; the same rule
   applies to manager feedback shown to the employee.
4. **Given** a confirmed appraisal, **When** it is marked done, **Then** its state is done and the
   employee's next appraisal date is set to the completion date plus the configured frequency.
5. **Given** an appraisal in any non-done state, **When** it is cancelled, **Then** its state is
   cancelled and it no longer counts as the employee's open appraisal.
6. **Given** an employee with two past appraisals, **When** their form is opened, **Then** both
   appraisals are listed as history with their dates and final states.

---

### User Story 5 - Employee referrals into recruitment (Priority: P3)

An employee refers a candidate to a published job position, entering the candidate's name and
contact details. The system creates a linked applicant in the recruitment pipeline for that job,
attributed to the referrer. The referrer can see the status of their referral as it moves through
the recruitment stages, and the system keeps a running count of successful/total referrals per
referrer.

**Why this priority**: Referrals is a convenience layer on top of Recruitment (US3) and delivers
value only once the pipeline exists. Lowest coupling, highest optionality.

**Independent Test**: With a published job, have an employee submit a referral for a candidate.
Confirm an applicant is created for that job, linked to the referrer, and tagged as referred. Move
the applicant through two stages and confirm the referrer's referral view reflects the new status.
Confirm the referrer's referral count reflects the referral.

**Acceptance Scenarios**:

1. **Given** a published job position, **When** an employee submits a referral with a candidate name
   and contact details, **Then** an applicant is created for that job, its source indicates a
   referral, and it is linked to the referring employee.
2. **Given** an unpublished job position, **When** an employee tries to refer a candidate to it,
   **Then** the referral is not allowed.
3. **Given** a referral whose applicant advances through recruitment stages, **When** the referrer
   views their referrals, **Then** each referral shows the current stage/status of its applicant.
4. **Given** a referrer with three referrals, **When** their referral count is read, **Then** it
   reflects three referrals (and separately how many reached a hired outcome).
5. **Given** a referral's applicant is converted to an employee (US3), **When** the referrer views
   their referrals, **Then** that referral is shown as successful.

---

### User Story 6 - Fleet vehicles, drivers, contracts and alerts (Priority: P3)

A fleet manager records vehicles, each with a model and brand, and moves each vehicle through its
lifecycle state (new request → to order → ordered → registered, plus downgraded / reserved / waiting
list). A vehicle can be assigned a driver who is an employee. The manager logs odometer readings
over time, records leasing and insurance contracts with an amount and an expiry date, and logs
service events. The system surfaces contracts that are expired or expiring soon as alerts.

**Why this priority**: Fleet is an independent asset-management area that only touches HR through the
driver link. It can ship last without blocking anything else.

**Independent Test**: Seed a brand and two models. Create a vehicle, set its state to registered,
and assign an employee as driver. Add two odometer logs and confirm the latest reading is shown.
Add an insurance contract expiring in 10 days and a leasing contract expired last month; confirm
both appear in the expiry alert list. Add a service log and confirm it is listed for the vehicle.

**Acceptance Scenarios**:

1. **Given** a vehicle brand and model, **When** the fleet manager creates a vehicle referencing
   that model, **Then** the vehicle is saved with its brand derived from the model and starts in the
   new-request state.
2. **Given** a vehicle, **When** the manager changes its state along the lifecycle, **Then** the new
   state is stored and the change is recorded.
3. **Given** a vehicle, **When** the manager assigns an employee as the driver, **Then** the driver
   link is stored and the vehicle appears among that employee's assigned vehicles.
4. **Given** a vehicle with several odometer logs, **When** the vehicle is viewed, **Then** the most
   recent odometer value and its date are shown and the full history is available.
5. **Given** a leasing or insurance contract with an expiry date within the alert window or in the
   past, **When** the fleet alerts are viewed, **Then** that contract is listed as expiring or
   expired with the vehicle and days remaining.
6. **Given** a vehicle, **When** the manager logs a service event with a type, date, and amount,
   **Then** it is recorded in the vehicle's service history.
7. **Given** a user without the Fleet Manager group, **When** they attempt to create or modify a
   vehicle, **Then** the action is denied.

---

### Edge Cases

- **Employee with no user**: an employee record need not be linked to a login user; "current user's
  employee" resolves to nothing for such users and HR areas that need it prompt to link one.
- **User linked to multiple employees**: a login user maps to at most one employee per company;
  attempting to link a second employee in the same company is rejected.
- **Circular management**: setting an employee's manager to a subordinate (directly or transitively)
  is rejected so the org chart cannot loop.
- **Department/job headcount**: deleting or archiving an employee decreases the job's current
  headcount; current headcount may legitimately exceed expected headcount and is shown as over
  target rather than blocked.
- **Contract dates**: a contract end date before its start date is rejected; a trial-period end
  outside the contract window is rejected; only one running contract per employee at a time.
- **Skill level mismatch**: a skill level must belong to the same skill type as the skill; the same
  skill cannot be added twice to one employee.
- **Leave spanning year boundary / allocation change**: duration and balance are computed against
  the allocation and calendar in effect on each day of the leave.
- **Leave with zero counted days**: a request that falls entirely on weekends/public holidays counts
  as zero duration and is rejected as having no effect.
- **Approver is the requester**: an employee who is also a manager cannot be the sole approver of
  their own leave or appraisal; it escalates to the next approver.
- **Refusing an already-approved leave**: restores the consumed balance.
- **Applicant converted twice**: the second "create employee" is a no-op that returns the existing
  employee.
- **Referral to a job that is later unpublished**: existing referrals remain visible and tracked;
  no new referrals can be added.
- **Appraisal with no manager**: an employee with no manager assigned routes manager feedback and
  approval to the HR officer.
- **Vehicle driver who leaves the company**: the driver link is retained historically; the vehicle
  is flagged as needing reassignment.
- **Odometer log lower than a previous reading**: allowed but flagged as inconsistent.
- **Multi-company**: every operational record (employee, department, job, contract, leave,
  allocation, applicant, appraisal, referral, vehicle) carries a company and is only visible within
  that company's scope. Configuration catalogs carry an optional `company_id`: `NULL` = shared
  across all companies, a set value = visible only in that company. Per the Odoo 19.0 reference,
  skill type / skill / skill level, employee categories, applicant refusal reasons, and vehicle
  brands/models are global (no `company_id`); leave types, recruitment stages, and contract types
  carry a nullable `company_id`.

## Requirements *(mandatory)*

### Functional Requirements

#### Employees, departments, jobs, tags (P1)

- **FR-001**: The system MUST provide an Employee record with fields grouped into Personal (name,
  photo, gender, date of birth, marital status, personal contact address, personal email, personal
  phone, emergency contact name and phone), Work (work email, work phone, department, job position,
  job title, work location, manager, coach, company), Private (nationality, identification number,
  bank account details, home address, number of dependants), and HR Settings (linked login user,
  employee category tags, active/archived flag) groupings.
- **FR-002**: The system MUST provide a Department record that references an optional parent
  department, forming a navigable hierarchy, and MUST reject a parent assignment that would create a
  cycle.
- **FR-003**: The system MUST provide a Job Position record with a title, a department, an expected
  headcount, and a derived current headcount equal to the count of active employees holding that job.
- **FR-004**: The system MUST provide an Employee Category (tag) record and allow an employee to
  carry zero or more tags.
- **FR-005**: The system MUST allow an employee to be linked to at most one login user per company
  and MUST expose a way to resolve the employee record of the currently authenticated user. The
  link MUST be set explicitly by an HR Officer or HR Administrator; the system MUST NOT
  auto-provision a login user when an employee is created.
- **FR-006**: The system MUST allow each employee to have a manager (another employee) and a coach
  (another employee), independently, and MUST reject a manager assignment that creates a management
  cycle.
- **FR-007**: The system MUST provide an org-chart presentation for an employee showing their
  management chain upward and their direct reports downward.
- **FR-008**: The system MUST present employees in both a card view and a list view, and MUST
  provide an employee form exposing the four field groupings from FR-001 as tabs.
- **FR-009**: Employee, department, and job records MUST be company-scoped and multi-company aware:
  a user only sees records for companies they are allowed to access.
- **FR-010**: All Employees screens MUST render translated labels and support right-to-left layout
  when the active language is right-to-left, consistent with features 002 and 005.

#### Contracts (P1)

- **FR-011**: The system MUST provide a Contract record linked to an employee with a wage, a
  contract type, a start date, an optional end date, and an optional trial-period end date.
- **FR-012**: A Contract MUST have a state of draft, running, expired, or cancelled, with allowed
  transitions draft→running, running→expired, running→cancelled, draft→cancelled, and
  cancelled/expired→draft (re-open); every transition MUST be recorded.
- **FR-013**: The system MUST reject a contract whose end date precedes its start date, and a
  trial-period end date outside the start–end window.
- **FR-014**: The system MUST enforce at most one running contract per employee at a time.
- **FR-015**: The system MUST provide a lookup that returns an employee's current running contract
  (the running contract whose date range contains today, or the latest running contract).
- **FR-016**: A running contract whose end date is in the past MUST be presented as expired.

#### Skills (P1)

- **FR-017**: The system MUST provide a Skill Type record, a Skill record (belonging to a skill
  type), and a Skill Level record (belonging to a skill type, with an ordering and a progress
  percentage).
- **FR-018**: The system MUST provide an Employee Skill record linking an employee to a skill and a
  skill level, MUST reject a level that does not belong to the skill's skill type, and MUST reject
  the same skill being added twice to one employee.
- **FR-019**: The employee form MUST display the employee's skills grouped by skill type with each
  skill's level.

#### Time Off — configuration (P2)

- **FR-020**: The system MUST provide a Leave Type record configuring: the unit (days or hours),
  paid or unpaid, whether an allocation is required before requesting, whether negative balances are
  allowed, and the approval mode (no approval / manager approval / HR-officer approval / manager then
  second approval).
- **FR-021**: The system MUST provide a working-time calendar per company (standard weekly working
  days and hours) used to compute leave durations, and MUST provide a Public Holiday record
  (date range, company or global) excluded from leave durations.
- **FR-022**: The system MUST provide a Leave Allocation record linking an employee and a leave type
  to an amount, of mode regular (fixed amount) or accrual (a rate added per period up to an optional
  maximum), with an optional validity period.
- **FR-023**: An accrual allocation MUST increase the allocated amount by its rate as each accrual
  period elapses, never exceeding its configured maximum.

#### Time Off — requests and balances (P2)

- **FR-024**: The system MUST provide a Leave Request record linking an employee and a leave type to
  a date/time range, with states to-approve → (second-approval) → approved, and refused reachable
  from to-approve, second-approval, or approved.
- **FR-025**: The system MUST compute a leave request's duration from the company working calendar,
  excluding non-working weekdays and public holidays, expressed in the leave type's unit.
- **FR-026**: The system MUST reject a leave request that overlaps in time with another
  non-refused leave request for the same employee.
- **FR-027**: The system MUST reject a leave request whose duration is zero after calendar and
  holiday exclusion.
- **FR-028**: The system MUST route approval per the leave type's approval mode. The approving actor
  is a login user: the user linked to the employee's manager employee; if there is no manager, or
  the manager has no linked user, approval falls to any HR Officer in the same company scope. A
  requester MUST NOT be the sole approver of their own request (it escalates to an HR Officer).
- **FR-029**: The system MUST compute, per employee and leave type, a balance = allocated − (taken +
  pending) and MUST reject a request exceeding the available balance when the leave type disallows
  negative balances.
- **FR-030**: Approving a request MUST consume balance for that employee and leave type; refusing a
  previously approved request MUST restore it.
- **FR-031**: The system MUST provide a calendar presentation of leave requests; a plain employee
  sees only their own, a manager additionally sees their team's, an HR officer sees all in scope.

#### Recruitment (P2)

- **FR-032**: The Job Position record MUST carry a published flag; only a published job can be a
  recruitment or referral target for external/candidate-facing flows.
- **FR-033**: The system MUST provide a Recruitment Stage record with a name, a sequence ordering
  the pipeline columns, and a boolean "hired stage" flag; an applicant whose stage has the hired
  flag set is considered hired and is eligible for conversion (FR-038).
- **FR-034**: The system MUST provide a Recruitment Source record identifying where an applicant
  came from (including a value denoting an employee referral).
- **FR-035**: The system MUST provide an Applicant record with the candidate name, email, phone, the
  job position applied for, the department (derived from the job, overridable), a recruitment source,
  a recruitment stage, and zero or more assigned interviewers (users).
- **FR-036**: The system MUST present applicants for a job as a Kanban pipeline grouped by stage in
  sequence order, and MUST allow moving an applicant between stages.
- **FR-037**: The system MUST provide an Applicant Refusal Reason record and allow marking an
  applicant refused with a reason; a refused applicant MUST leave the active pipeline while retaining
  its data and reason.
- **FR-038**: The system MUST provide an "create employee from applicant" action that creates an
  employee carrying the applicant's name, contact details, job position, and department, links the
  applicant to that employee, and is idempotent (a second run returns the existing employee). The
  action MUST NOT create a login user for the new employee.

#### Appraisals (P3)

- **FR-039**: The system MUST provide an Appraisal Template record with an ordered set of feedback
  sections (each a titled prompt) and a default appraisal frequency in months.
- **FR-040**: The system MUST provide an Appraisal record linking an employee (appraisee) and a
  manager (appraiser) with a state of new, pending confirmation, confirmed, done, or cancelled, and
  MUST record every state transition.
- **FR-041**: Launching an appraisal MUST instantiate the template's feedback sections on the
  appraisal for both the employee side and the manager side.
- **FR-042**: The system MUST store employee feedback and manager feedback separately, each with its
  own published/visible flag; one side's feedback MUST NOT be readable by the other side until that
  side sets its feedback visible.
- **FR-043**: Marking an appraisal done MUST set the appraised employee's next appraisal date to the
  completion date plus the applicable frequency (from the template or an employee/department
  override).
- **FR-044**: The employee form MUST show that employee's appraisal history (date and final state
  of each past appraisal), and only the current non-done appraisal counts as open.
- **FR-045**: An appraisal MAY be cancelled from any non-done state; a cancelled appraisal does not
  count as open and does not change the next appraisal date.

#### Referrals (P3)

- **FR-046**: The system MUST allow an employee to submit a Referral for a published job position
  with a candidate name and contact details.
- **FR-047**: Submitting a referral MUST create a linked Applicant (FR-035) for that job with the
  recruitment source set to the employee-referral value and a link back to the referring employee.
- **FR-048**: A referral MUST expose the current recruitment stage/status of its applicant to the
  referrer as the applicant advances.
- **FR-049**: The system MUST maintain, per referring employee, a count of total referrals and a
  count of referrals that resulted in a hire (applicant converted to employee).
- **FR-050**: A referral MUST NOT be creatable against an unpublished job; referrals already made
  against a job that is later unpublished remain visible and tracked.

#### Fleet (P3)

- **FR-051**: The Fleet capability MUST be delivered as a separate `dodoo/addons/fleet/` addon
  depending on the HR addon for the employee/driver link.
- **FR-052**: The system MUST provide a Vehicle Brand record, a Vehicle Model record (belonging to a
  brand), and a Vehicle record referencing a model (with brand derived from the model), a licence
  plate, and a company.
- **FR-053**: A Vehicle MUST have a state of new request, to order, ordered, registered, downgraded,
  reserved, or waiting list; changes MUST be recorded.
- **FR-054**: A Vehicle MAY be assigned a driver that is an employee; the vehicle MUST then appear
  among that employee's assigned vehicles, and a former driver link MUST be retained historically.
- **FR-055**: The system MUST provide an Odometer Log record (vehicle, value, date) and MUST expose
  the most recent reading per vehicle; a reading lower than a prior one is allowed but flagged.
- **FR-056**: The system MUST provide a Vehicle Contract record of type leasing or insurance with an
  amount, a start date, and an expiry date, and MUST list contracts whose expiry date is within a
  configurable alert window or already past, with the vehicle and days remaining.
- **FR-057**: The system MUST provide a Vehicle Service Log record (vehicle, service type, date,
  amount, notes) forming the vehicle's service history.

#### Security groups and record rules (cross-cutting)

- **FR-058**: The system MUST define HR security groups Employee, HR Officer, and HR Administrator
  (each a superset of the previous), plus an independent Fleet Manager group.
- **FR-059**: A user in only the Employee group MUST be able to read the public directory (names,
  photos, work contact, department, job, manager) of all employees in their company but MUST NOT
  read any other employee's Private grouping, contracts, wage, or appraisals-as-employee.
- **FR-060**: A user in only the Employee group MUST be able to read and manage their own leave
  requests, their own referrals, and their own appraisal feedback, and MUST be able to read their
  own contract and private info (read-only).
- **FR-061**: A manager MUST additionally be able to see the leave requests and appraisals of the
  employees who report to them (their team), for approval.
- **FR-062**: An HR Officer MUST be able to read and manage employees, contracts, time off,
  recruitment, and appraisals within their company scope; an HR Administrator MUST additionally
  manage configuration (leave types, stages, skill types, templates, working calendars, security
  assignments).
- **FR-063**: Fleet records MUST be readable by HR Officers and fully managed only by the Fleet
  Manager group; a driver MAY read the vehicle(s) assigned to them.
- **FR-064**: Every record rule MUST enforce company scope in addition to the role-based conditions
  above.
- **FR-064a**: Configuration catalog records (leave types, recruitment stages, contract types, and
  any other catalog that carries a nullable `company_id`) MUST be visible when their `company_id` is
  `NULL` (shared) or equals a company the user may access; catalogs modelled as global in Odoo 19.0
  (skill type / skill / skill level, employee categories, applicant refusal reasons, vehicle
  brands/models) carry no `company_id` and are visible to all companies.

#### Navigation and menus (cross-cutting)

- **FR-064b**: Each area MUST contribute its own top-level application menu — Employees,
  Recruitment, Time Off, Appraisals, Referrals, and Fleet — with area sub-menus, following the
  menu-contribution pattern already used by the accounting addon. The generic metadata-driven model
  sidebar from feature 002 MUST remain available and MUST NOT be removed by this feature. Menu
  entries MUST be gated by the viewer's HR / Fleet groups (an Employee-only user does not see the
  Recruitment or Fleet configuration menus).

#### Input validation, logging, workflow integrity (cross-cutting)

- **FR-065**: Every HTTP/RPC entry point that creates or mutates an HR or Fleet record MUST validate
  inputs at the boundary using whitelist-based validation before any processing; unknown fields and
  out-of-range values MUST be rejected.
- **FR-066**: Every state transition and every approval/refusal action (contract state, leave
  approval steps, appraisal state, applicant stage change, referral status change, vehicle state)
  MUST emit a structured JSON log entry carrying a correlation ID, the actor, the record, and the
  from/to state.
- **FR-067**: All workflow actions MUST be authorization-checked: the acting user MUST hold a group
  and/or relationship (manager of, HR officer, fleet manager, record owner) that permits the
  transition, else it is denied and logged.
- **FR-067a**: Every state transition MUST re-check the record's current state server-side against
  the transition's expected source state before applying it; if the record has already moved on
  (a concurrent or stale action), the transition MUST be rejected with a conflict error and no side
  effects, and the rejection MUST be logged per FR-066. Plain (non-workflow) field edits retain the
  web client's existing save semantics from feature 002.
- **FR-068**: A fresh install MUST seed sample data: a small department tree, several job positions,
  a set of leave types, skill types with skills and levels, a set of recruitment stages (including
  one flagged as a hired stage), at least one appraisal template, and a set of vehicle brands with
  models.

### Key Entities *(include if feature involves data)*

- **Employee**: a person the company employs or engages. Personal / work / private / HR-settings
  attributes (FR-001). Relates to Department, Job Position, Employee Category (tags), a login user
  (0..1 per company), a manager Employee, a coach Employee, a company. Modelled on Odoo `hr.employee`.
- **Department**: an organisational unit with an optional parent Department (hierarchy). Has a
  manager Employee and a company. Modelled on Odoo `hr.department`.
- **Job Position**: an open or filled role with a title, department, expected headcount, derived
  current headcount, and a published flag. Modelled on Odoo `hr.job`.
- **Employee Category**: a free tag applied to employees. Modelled on Odoo `hr.employee.category`.
- **Contract**: an employment contract for an employee — wage, contract type, start/end/trial dates,
  state (draft/running/expired/cancelled). Modelled on Odoo `hr.contract`.
- **Skill Type / Skill / Skill Level**: a competency taxonomy. A Skill belongs to a Skill Type; a
  Skill Level belongs to a Skill Type and has an order and a progress percentage. Modelled on Odoo
  `hr.skill.type`, `hr.skill`, `hr.skill.level`.
- **Employee Skill**: an employee's proficiency — links Employee → Skill → Skill Level. Modelled on
  Odoo `hr.employee.skill`.
- **Working-Time Calendar**: a company's standard weekly working days and hours, used for leave
  duration. Modelled on Odoo `resource.calendar`.
- **Public Holiday**: a non-working date range, global or per company, excluded from leave duration.
  Modelled on Odoo `resource.calendar.leaves` (global leaves).
- **Leave Type**: configuration for a category of time off — unit (days/hours), paid/unpaid,
  allocation-required, negative-balance policy, approval mode. Modelled on Odoo `hr.leave.type`.
- **Leave Allocation**: entitlement granted to an employee for a leave type — amount, mode
  (regular/accrual), accrual rate/cap, validity. Modelled on Odoo `hr.leave.allocation`.
- **Leave Request**: a time-off request — employee, leave type, date/time range, computed duration,
  state (to-approve / second-approval / approved / refused). Modelled on Odoo `hr.leave`.
- **Recruitment Stage**: a named, sequenced column in the recruitment pipeline, with a boolean
  "hired stage" flag marking the outcome column(s). Modelled on Odoo `hr.recruitment.stage`
  (`hired_stage`).
- **Recruitment Source**: where an applicant originated (including "employee referral"). Modelled on
  Odoo `hr.recruitment.source` / `utm.source`.
- **Applicant**: a candidate for a job — name, contact, job position, department, source, stage,
  interviewers, refused flag + refusal reason, linked employee once hired. "Hired" is derived from
  the applicant's stage carrying the hired-stage flag; there is no separate applicant state machine
  beyond stage + refused. Modelled on Odoo `hr.applicant`.
- **Applicant Refusal Reason**: a reusable reason for rejecting an applicant. Modelled on Odoo
  `hr.applicant.refuse.reason`.
- **Appraisal Template**: ordered feedback sections + default frequency (months). Modelled on Odoo
  `hr.appraisal` templates / `hr_appraisal` config.
- **Appraisal**: an appraisal cycle instance for an employee — appraisee, appraiser, state
  (new / pending confirmation / confirmed / done / cancelled), employee feedback + visible flag,
  manager feedback + visible flag, dates. Modelled on Odoo `hr.appraisal`.
- **Referral**: an employee's referral of a candidate to a published job — referrer Employee, job,
  candidate details, linked Applicant, derived status. Modelled on Odoo `hr_referral`
  (`hr.referral.*`).
- **Vehicle Brand / Vehicle Model**: catalog of makes and models; a Model belongs to a Brand.
  Modelled on Odoo `fleet.vehicle.model.brand`, `fleet.vehicle.model`.
- **Vehicle**: a fleet asset — model (brand derived), licence plate, company, state
  (new request / to order / ordered / registered / downgraded / reserved / waiting list), current
  driver Employee. Modelled on Odoo `fleet.vehicle`.
- **Odometer Log**: a dated mileage reading for a vehicle. Modelled on Odoo `fleet.vehicle.odometer`.
- **Vehicle Contract**: a leasing or insurance contract for a vehicle — amount, start date, expiry
  date, derived expiry alert. Modelled on Odoo `fleet.vehicle.log.contract`.
- **Vehicle Service Log**: a dated service event for a vehicle — service type, amount, notes.
  Modelled on Odoo `fleet.vehicle.log.services`.
- **Security groups**: Employee, HR Officer, HR Administrator (nested), and Fleet Manager
  (independent). Bound to record rules that combine role conditions with company scope. Modelled on
  Odoo `hr.group_hr_user` / `hr.group_hr_manager` and `fleet.fleet_group_manager`.
- **Reused core entities**: `res.users`, `res.groups`, `res.company`, `ir.rule`-equivalent record
  rules, `res.lang` (from 005) for translation/RTL, and `res.currency` for monetary amounts (wage,
  fleet amounts) — read only, no journal/posting. The feature adds records and rules in these
  existing models; it introduces no parallel user/group/company/currency structures and does not
  depend on the accounting addon.

### Security Requirements

- **SEC-001**: The system MUST validate all inputs at HTTP/RPC boundaries using whitelist-based
  validation (allowed field names, types, enumerations, and numeric/date ranges) before any
  downstream processing, for every HR and Fleet create/update/action endpoint.
- **SEC-002**: The system MUST enforce least-privilege: the HR groups (Employee / Officer /
  Administrator) and the Fleet Manager group MUST gate every model operation and workflow action, and
  no endpoint may perform an action the acting user's groups and relationships do not permit.
- **SEC-003**: Record rules MUST ensure a plain Employee cannot read another employee's sensitive
  data — Private grouping, contracts, wage, and appraisals-as-employee — and that time-off and
  appraisals of others are visible only to a manager for their own team and to HR Officers/Admins in
  scope.
- **SEC-004**: Every mutation and workflow endpoint MUST require an authenticated session and MUST
  re-check authorization server-side on each call (no reliance on the client hiding actions).
- **SEC-005**: The system MUST comply with OWASP Top 10; a checklist review is REQUIRED before
  implementation, with attention to A01 Broken Access Control (cross-employee data exposure, approval
  bypass), A03 Injection (free-text feedback, candidate details, notes, seed data), and A04 Insecure
  Design (approval workflow escalation and self-approval).
- **SEC-006**: Personal data (private info, bank details, identification numbers, personal contact
  details, appraisal feedback) MUST NOT appear in logs or error messages; structured logs record
  identifiers and state, not payloads.
- **SEC-007**: Secrets and credentials MUST NOT appear in source, seed data, logs, or error
  messages.

### Performance Requirements

- **PERF-001**: The employee directory list/search MUST return the first page (50 records) in
  under 500 ms for a company of up to 2,000 employees under normal load, including applied search
  filters on name, department, and job.
- **PERF-002**: Computing an employee's time-off balance for a leave type (allocated − taken −
  pending, across allocations and the working calendar) MUST complete in under 300 ms for an
  employee with up to 5 years of history under normal load.
- **PERF-003**: Rendering the recruitment Kanban pipeline for a job with up to 500 applicants across
  stages MUST return in under 800 ms.
- **PERF-004**: The fleet expiry-alert list MUST compute in under 500 ms for up to 1,000 vehicles
  and 5,000 contracts.
- **PERF-005**: No known regressions permitted; benchmark tests for the directory list/search path
  and the time-off balance computation MUST run in CI, and the existing targets of features 001–005
  MUST be unaffected.

### Accessibility Requirements

- **ACC-001**: All HR and Fleet screens MUST meet WCAG 2.1 AA colour-contrast ratios (≥ 4.5:1 normal
  text, ≥ 3:1 large text) in both left-to-right and right-to-left layouts.
- **ACC-002**: All interactive elements — including the Kanban pipeline (drag between stages), the
  org chart, the time-off calendar, and every workflow action button — MUST be fully
  keyboard-operable, with a keyboard alternative to drag-and-drop for moving applicants between
  stages.
- **ACC-003**: Workflow state (contract state, leave approval step, appraisal state, applicant
  stage, vehicle state, contract expiry alert) MUST NOT be conveyed by colour alone; text/ARIA
  labels MUST accompany every status indicator, and the calendar and org chart MUST expose an
  accessible name and structure to assistive technology.
- **ACC-004**: Right-to-left layouts MUST preserve a logical keyboard tab order and set the correct
  language and direction attributes, consistent with feature 005.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh install an HR officer can create a department tree, a job position, and 10
  employees, and view them in the card view, list view, and org chart, in under 15 minutes with no
  configuration beyond the seeded data.
- **SC-002**: 100% of employee records enforce company scope — a user restricted to one company sees
  zero records from another company across employees, departments, jobs, contracts, leaves,
  applicants, appraisals, referrals, and vehicles.
- **SC-003**: For every leave type approval mode, a request reaches its terminal state (approved or
  refused) only through the configured approval steps, and 100% of approved paid requests change the
  employee's balance by exactly the calendar-computed duration.
- **SC-004**: 100% of leave requests that overlap an existing non-refused request for the same
  employee, or that compute to zero duration, are rejected.
- **SC-005**: An applicant moved to a hired state and converted produces exactly one employee with
  the carried-over name, contact, job, and department; running the conversion twice still yields
  exactly one employee.
- **SC-006**: A plain Employee-group user can retrieve zero other employees' Private-grouping
  fields, contracts, wages, or appraisals-as-employee in 100% of attempts, while retrieving 100% of
  their own.
- **SC-007**: A manager can retrieve 100% of their direct reports' pending leave requests and open
  appraisals for approval, and zero pending items for employees outside their team (unless also an
  HR Officer).
- **SC-008**: Every state transition and approval/refusal action across all six areas produces a
  structured JSON log entry with a correlation ID, actor, record identifier, and from/to state —
  verified for 100% of transition types.
- **SC-009**: The employee directory list/search returns the first 50 results in under 500 ms at
  2,000 employees, and time-off balance computation completes in under 300 ms at 5 years of history,
  measured by CI benchmarks.
- **SC-010**: Every workflow (contract lifecycle, time-off approval + accrual, recruitment pipeline
  + conversion, appraisal cycle, referral tracking, vehicle lifecycle + alerts) has passing unit,
  integration, and end-to-end tests.
- **SC-011**: An automated accessibility audit of every HR and Fleet screen reports zero WCAG 2.1 AA
  violations in both left-to-right and right-to-left layouts, and every workflow action and the
  Kanban stage move are operable by keyboard alone.
- **SC-012**: The fleet expiry-alert list surfaces 100% of leasing/insurance contracts expiring
  within the alert window or already expired, each with the correct vehicle and days-remaining
  value.

## Assumptions

- **Odoo reference**: the spec reproduces the *behaviour* of the Odoo 19.0 hr, hr_contract,
  hr_skills, hr_org_chart, hr_holidays, hr_recruitment, hr_appraisal, hr_referral, and fleet addons
  (models, field groupings, states, menus, security groups, workflows, and view types). Where the
  Odoo source is available at `../odoo-19.0` it is the authority on field-level detail during
  planning; where it is not, established Odoo 19.0 semantics are assumed.
- **Architecture**: implemented as `dodoo/addons/hr/` (Employees + Contracts + Skills + Time Off +
  Recruitment + Appraisals + Referrals) and `dodoo/addons/fleet/`, on the existing FastAPI routing,
  SQLAlchemy Core async, Pydantic v2, vanilla-JS SPA, and the ORM / view / record-rule patterns from
  001-erp-core and 002-web-ui. The internal split of the `hr` addon into sub-areas (and whether
  Referrals/Fleet are further separated) is a planning decision; the delivered addon boundary is
  `hr` + `fleet`.
- **Scope boundaries — explicitly out of scope**: payroll and payslips; salary structures and rules;
  attendances / kiosk / check-in; timesheets; expenses; employee self-service portal and public
  website job board; recruitment email gateway / CV parsing; appraisal surveys / 360°
  questionnaires; e-signature of contracts and documents; skills-based recruitment matching;
  fleet accounting integration (vendor bills, journal entries) and fuel-card imports; fleet GPS /
  telematics; digest emails, chatter/mail threads, and activity scheduling. These may be later
  features.
- **Contracts**: a fixed list of contract types is seeded (e.g. Permanent, Fixed-term, Internship);
  wage is a plain monetary amount in the company currency with no salary-structure computation.
- **Time Off**: one standard working-time calendar per company is seeded (Mon–Fri, 8h/day); accrual
  is a simple fixed-rate-per-period model (e.g. N units per month) with an optional cap, not Odoo's
  full multi-level accrual plans with milestones. Public holidays are seeded empty and configured by
  an HR Administrator. Leave duration is computed in the employee's/company calendar; per-employee
  calendars are out of scope for this cycle.
- **Recruitment**: applicants are created in-app or via the data API — there is no inbound email or
  form capture. "Published" is a boolean on the job with no external portal in this cycle; it exists
  so Referrals has a valid target set and to model the Odoo flag.
- **Appraisals**: feedback sections are free-text prompts and free-text answers; there is no scoring,
  rating scale, or competency roll-up. Appraisal frequency resolves from the template, overridable
  per employee or department.
- **Referrals**: referral "points"/gamification and reward catalogues from Odoo `hr_referral` are
  out of scope; only the referral → applicant link, status tracking, and per-referrer counts are in
  scope. Referrals depend on the Recruitment area being present.
- **Fleet**: contract and service amounts are recorded as plain monetary values with no posting to
  accounting; the expiry alert window is a single configurable number of days (default 30). Fleet
  depends on the HR addon for the employee/driver link only.
- **Security model**: the three nested HR groups plus the independent Fleet Manager group are seeded
  and assigned via configuration by an HR Administrator; "team" for a manager means the transitive
  set of employees reporting to them through the manager relationship. Record rules reuse the
  `ir.rule`-equivalent mechanism from 001-erp-core.
- **Multi-company & localization**: every operational record carries `company_id` and obeys the
  multi-company visibility rules from 001; screens consume the translation/RTL layer from 002/005.
  Monetary fields (wage, fleet contract/service amounts) are plain amounts in the company currency
  (`res.currency`, provided by base/005) with no accounting posting; the `hr` and `fleet` addons do
  **not** depend on the 003-accounting (`account`) addon.
- **Dependencies**: requires the completed 001-erp-core (models, record rules, HTTP/RPC, users &
  groups), 002-web-ui (generic view architecture, list/form/sidebar), and 005-localization-settings
  (language, RTL, company currency/country). This feature extends the web client with two new
  generic, metadata-driven view types — **Kanban** and **Calendar** — reusable by any model; the
  employee card view is the Kanban view type applied to `hr.employee`. The **org chart** is a
  bespoke widget on the employee form (per Odoo `hr_org_chart`), not a generic view type. No
  dependency on 003-accounting.
- **ADRs to be filed during planning**: the contract-state engine; the time-off approval + accrual
  design; the appraisal cycle model; and the fleet contract/alert model.

## Out of Scope

- Payroll, payslips, salary structures/rules, and any salary computation beyond a stored wage.
- Attendances, kiosk check-in/out, timesheets, and expense management.
- Employee self-service portal, public website job board, and any candidate-facing web pages.
- Recruitment inbound email gateway, CV/résumé parsing, and application forms.
- Appraisal surveys, rating scales, scoring, 360° questionnaires, and goal/objective tracking.
- E-signature of contracts, offers, or documents.
- Referral gamification: points, levels, reward catalogue, and reward redemption.
- Fleet integration with accounting (vendor bills, journal entries, analytic accounting), fuel-card
  imports, and GPS/telematics.
- Chatter/message threads, activity scheduling, digest emails, and notification emails for any area.
- Per-employee working calendars and Odoo's full multi-milestone accrual plans.
- Additional HR sub-applications not listed (Lunch, Fleet expenses, Employee Contracts e-sign,
  Planning, Learning/e-learning).
