# Contract: Security Groups & Record Rules

## Groups (`res.groups`, seeded idempotently by `name`)

| name | full_name | Grants |
|------|-----------|--------|
| HR Employee | Human Resources / Employee | read public directory; manage own leave/referrals/appraisal-feedback; read own contract + private info |
| HR Officer | Human Resources / Officer | + manage employees, contracts, time off, recruitment, appraisals in company scope; approve team leave/appraisals |
| HR Administrator | Human Resources / Administrator | + manage config catalogs, working calendars, security assignment, cron endpoints |
| Fleet Manager | Fleet / Manager | full fleet management + fleet cron endpoints |

Nesting materialised at assignment: `assign_hr_group(env, uid, level)` inserts
`res_users_groups_rel` rows for every ancestor (`employee` ⊂ `officer` ⊂ `administrator`).
`Fleet Manager` is independent (a Fleet Manager need not be an HR user; grant `HR Officer` read of
fleet via a dedicated rule, not group nesting).

## `ir_model` sync

`data/ir_model_sync.py` (each addon): `INSERT INTO ir_model (name, table_name) VALUES (:n, :t)
ON CONFLICT (name) DO NOTHING` for every model the addon defines. Runs before `data/rules.py`.

## `ir.rule` rows (`domain_filter` JSON, bound to groups via `ir_rule_group_rel`)

`uid` in a domain is substituted by `AccessEnforcer` at query time via the standard
`employee_id.user_id` style dotted path (already supported by `compile_domain`). Company scope:
`allowed` = the set of company ids the user may access (single-company today → `[user_company_id]`).

### hr.employee
- **HR Employee** (perm_read): `[["company_id","in",<allowed>]]` — company scope only; the
  Private-group + birthday/marital/contact fields are removed by `hr.employee.read()` unless
  `row.user_id == uid` or the caller is `HR Officer`+ (model-layer drop, research.md D4).
- **HR Officer / Administrator** (read+write+create+unlink): `[["company_id","in",<allowed>]]`.
- **no group**: `[["id","=",0]]` (deny-by-default, D4 gap fix).

### hr.contract, hr.leave (as employee), hr.appraisal (as employee), hr.referral
- **HR Employee**:
  - hr.contract: `["&",["company_id","in",<allowed>],["employee_id.user_id","=",uid]]` (read only)
  - hr.leave: `["&",["company_id","in",<allowed>],"|",["employee_id.user_id","=",uid],
    ["employee_id.manager_id.user_id","=",uid]]` (read+write+create)
  - hr.appraisal: same shape as hr.leave (owner OR manager)
  - hr.referral: `["&",["company_id","in",<allowed>],["referrer_id.user_id","=",uid]]`
- **HR Officer / Administrator**: `[["company_id","in",<allowed>]]` full.
- **no group**: `[["id","=",0]]`.

### hr.appraisal.feedback
- Read gated through the parent appraisal rule; additionally `hr.appraisal.feedback.read` /
  `search_read` drops rows where `is_visible = false` **and** `side != <caller's side>`
  (caller side = `employee` when `appraisal.employee_id.user_id == uid`, else `manager`).
- Write: only the owning side (`feedback_wrong_side` otherwise).

### Config catalogs
`hr.leave.type`, `hr.recruitment.stage`, `hr.recruitment.source`, `hr.contract.type`,
`hr.public.holiday`, `resource.calendar`, `resource.calendar.attendance`:
- **all HR groups** (read): `["|",["company_id","=",null],["company_id","in",<allowed>]]`
- **HR Administrator** (write+create+unlink): unrestricted.
Global catalogs (`hr.skill.type`, `hr.skill`, `hr.skill.level`, `hr.employee.category`,
`hr.applicant.refuse.reason`, `fleet.vehicle.model.brand`, `fleet.vehicle.model`): read for all
authenticated users; write for `HR Administrator` / `Fleet Manager` respectively.

### fleet.vehicle and fleet.* logs
- **Fleet Manager** (full): `[["company_id","in",<allowed>]]` (logs via `vehicle_id.company_id`).
- **HR Officer** (read): `[["company_id","in",<allowed>]]`.
- **driver** (read, any authenticated user): `[["driver_id.user_id","=",uid]]` on `fleet.vehicle`;
  logs readable when their parent vehicle is.
- **no group**: `[["id","=",0]]`.

## REST action group checks (defence in depth, SEC-004)

Every REST route re-checks membership server-side before acting, independent of the record rules:

| Route prefix | Required |
|--------------|----------|
| `POST /hr/contract/*/set-state` | `HR Officer`+ OR employee's manager |
| `POST /hr/leave/*/approve|refuse` | approver set (ADR-025) OR `HR Officer`+ |
| `POST /hr/applicant/*` | `HR Officer`+ |
| `POST /hr/appraisal/*` | `HR Officer`+ OR employee's manager |
| `POST /hr/referral/submit` | any authenticated user with an `hr.employee` |
| `POST /hr/cron/*` | `HR Administrator` |
| `POST /fleet/vehicle/*`, `POST /fleet/cron/*` | `Fleet Manager` |
| `GET /fleet/alerts` | `Fleet Manager` OR `HR Officer` |

## Menu gating (client-side, cosmetic)

`/web/core/info` is extended to return `hr_groups: ["HR Employee", ...]` and
`fleet_manager: bool` for the caller. `hr-menu.js` / `fleet-menu.js` sections carry a
`requires: "officer"|"administrator"|"fleet_manager"|null` key; `app.js` hides entries the caller
lacks. This is UX only — the record rules and REST checks are the enforcement.
