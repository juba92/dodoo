# Phase 0 Research: Human Resources

All Technical Context items were resolvable from the existing codebase (001–005) and the Odoo 19.0
reference behaviour. No `NEEDS CLARIFICATION` markers remained after `/speckit-clarify` (two passes,
8 decisions). This document records the design decisions, the patterns reused, and the OWASP review.

## D1 — ORM & model layer

**Decision**: Every HR/Fleet entity is a `dodoo.core.models.BaseModel` subclass with `Field`
declarations (`Char`, `Text`, `Integer`, `Boolean`, `Date`, `Datetime`, `Float`, `Monetary`,
`Selection`, `Many2one`, `One2many`, `Many2many`, `Json`). CRUD via the inherited classmethods;
custom workflow logic as additional classmethods invoked through `execute_kw` or REST routes.
Schema is applied by `MigrationRunner.install()` (idempotent `CREATE TABLE IF NOT EXISTS` +
`ADD COLUMN IF NOT EXISTS`; destructive type changes raise `SchemaConflictError`).

**Rationale**: This is exactly how `account` (11 models incl. state machines, immutability guards,
`super().write` overrides) and `localization` are built. No new ORM capability is needed.

**Alternatives rejected**: introducing SQLAlchemy ORM models or a repository layer — diverges from
the established `BaseModel` classmethod pattern and ADR-001.

**Notes / gaps found**:
- `Many2many` needs `relation_table`, `column1`, `column2`; the junction table is created by
  `MigrationRunner` when `relation_table` is set (see `res.users.group_ids`).
- `Monetary` is `NUMERIC(20,6)`, non-negative, default 0 — fits wage and fleet amounts. No
  `currency_id` coupling is enforced by the field; store `currency_id = Many2one("res.currency")`
  on the owning row (contract, vehicle-contract) for display, defaulting to the company currency.
- `Selection` stores `VARCHAR(64)`; validation against `choices` is **not** automatic in `coerce`
  (checked in `account` by explicit code) — workflow methods must validate the target value.
- There is no per-request transaction spanning multiple `create`/`write` calls; each commits.
  Multi-row operations (launch appraisal → N feedback rows; apply pack) follow the `account`
  precedent: order writes so a re-run is idempotent (guard queries before insert).

## D2 — HTTP surface

**Decision**: Two channels, matching `account`:
1. **JSON-RPC `execute_kw`** for model CRUD and any public classmethod — the SPA already speaks it.
   `_object_execute_kw` injects `uid` only for `search`/`search_read`; other custom methods read the
   caller via `dodoo.core.context.get_uid()` (set by `LanguageMiddleware` from the session token) —
   the same mechanism `res.config.settings` uses (ADR-018/022).
2. **REST action routes** via `@route("/hr/…", methods=[…], auth="session")` for verbs that aren't a
   plain write: approve/refuse a leave, move an applicant stage, create-employee-from-applicant,
   set contract state, launch/confirm/close an appraisal, submit a referral, set vehicle state, and
   the three `/…/cron/*` idempotent advancers. Each returns `{"result": …}` or
   `{"error": str}` with `status_code=400`, like `account/http/__init__.py`.

**Rationale**: reuses the existing auth (`X-Session-Token`), correlation-ID middleware, and error
envelope. No new dispatcher.

**Alternatives rejected**: a bespoke `/hr/rpc` endpoint or GraphQL — second auth/validation path.

## D3 — Whitelist validation at the boundary (SEC-001, FR-065)

**Decision**: `hr/validators.py` and `fleet/validators.py` hold one Pydantic v2 `BaseModel` per
action payload (`extra="forbid"`, explicit types, `Literal[…]` for enums, `Field(ge=…, le=…)` and
`model_validator` for date ranges). REST handlers parse the request body through the matching model
before touching the ORM; `execute_kw` custom methods validate their `kwargs` the same way (a thin
`validate(payload_model, kwargs)` helper). Unknown fields → `422`/`DodooError`.

**Rationale**: Constitution III + FR-065. Pydantic v2 is already a dependency (FastAPI). Mirrors the
spirit of `localization`'s `_assert_active_lang` / `_assert_active_country` whitelists, generalised.

**Alternatives rejected**: hand-rolled `if key not in ALLOWED` checks per handler — repetitive and
error-prone; trusting `BaseModel.create` to drop unknown keys (it does drop them, but silently — the
spec requires *rejection*).

## D4 — Access control: groups + record rules

**Decision**:
- **Groups** (`res.groups`, seeded idempotently in `data/groups.py`): `HR Employee` ⊂ `HR Officer`
  ⊂ `HR Administrator` (nesting modelled by seeding a user's row into every ancestor group on
  assignment — dodoo `res.groups` has `name`, `full_name`, no implied-group graph, so nesting is
  materialised at assignment time by an `assign_hr_group(env, uid, level)` helper). `Fleet Manager`
  is independent. Membership check = the `account`/`localization` pattern:
  `SELECT 1 FROM res_users_groups_rel JOIN res_groups g … WHERE user_id=:uid AND g.name=:name`.
- **Record rules** (`ir.rule` rows in `data/rules.py`, `domain_filter` JSON, bound to groups via
  `ir_rule_group_rel`): enforced by `BaseModel.search`/`search_read` when `uid` is passed
  (`AccessEnforcer.get_merged_domain`). Domains (full list in `contracts/security-groups.md`):
  - `hr.employee` sensitive read: `HR Employee` sees rows where `user_id = <uid>` **or** the row is
    limited to non-sensitive fields — implemented as *two* models' worth of rules is overkill, so
    instead the **sensitive fields are gated in the model layer**: `hr.employee.read` drops the
    Private-group + `user_id`-only fields for non-owner non-officers (like `res.users.read` drops
    `password_hash`). The record rule keeps company scope + `active`.
  - `hr.contract`, `hr.leave` (as employee), `hr.appraisal` (as employee), `hr.referral`:
    `['|', ['employee_id.user_id','=',uid], ['<manager path>','=',uid]]` for `HR Employee`;
    unrestricted (company-scoped only) for `HR Officer`+.
  - Manager team access: `hr.leave` / `hr.appraisal` domain
    `['employee_id.manager_id.user_id','=',uid]` OR-ed in for approvers.
  - Every rule additionally ANDs `['company_id','in',<allowed company ids>]` (FR-064).
- **`ir_model` rows**: `ir.rule.model_id` FKs `ir_model`, which no framework code populates.
  `data/ir_model_sync.py` inserts `(name, table_name)` rows for each `hr.*` / `fleet.*` model
  (idempotent `ON CONFLICT (name) DO NOTHING`) before `data/rules.py` runs.

**Rationale**: uses the exact enforcement path from ADR-009 and the 001 access-rule tests. Gating
sensitive columns in `read` (not via a second "public employee" model) is the minimal faithful
analogue of Odoo's `hr.employee.public` without adding a mirror table and view.

**Alternatives rejected**: (a) an `hr.employee.public` mirror model — doubles the schema and every
view; (b) column-level SQL grants — dodoo uses one DB role; (c) relying on the SPA to hide fields —
violates SEC-004.

**Gap**: `AccessEnforcer.get_merged_domain` returns `None` when a model has *no* rules, meaning
"unrestricted". So a model with sensitive data MUST have at least one rule for every group, or an
un-grouped user could read it. `data/rules.py` seeds a deny-by-default `[[ 'id', '=', 0 ]]` rule for
the no-group case on sensitive models.

## D5 — Time-off duration & balance performance (PERF-002)

**Decision**: `_leave_duration` runs one SQL statement:
`generate_series(date_from::date, date_to::date, '1 day') AS d`, LEFT JOIN the company
`resource_calendar_attendance` on `extract(dow from d)`, LEFT JOIN `hr_public_holiday` on
`d BETWEEN date_from AND date_to`, count days where an attendance row exists and no holiday matches;
for `hour` unit multiply by the attendance `hour_to - hour_from` sum. Balance components are three
`SUM` queries (`hr_leave_allocation` where mode-resolved amount; `hr_leave` taken = `approved`;
pending = `to_approve|second_approval`) filtered by `(employee_id, leave_type_id)`. Indexes:
`idx_hr_leave_employee_type_state`, `idx_hr_leave_allocation_employee_type`,
`idx_hr_public_holiday_range`.

**Rationale**: set-based, so 5 years (~1,825 rows in the series, a handful of leaves) stays well
under 300 ms. Mirrors Odoo's `_get_number_of_days` intent without its Python interval loop.

**Alternatives rejected**: per-day Python iteration (fails PERF-002); a materialised balance column
(drift, needs triggers dodoo doesn't have).

## D6 — Directory search performance (PERF-001)

**Decision**: `hr.employee` list/search is `search_read` with `order` and `limit=50`, backed by
`idx_hr_employee_company_name (company_id, name)` and `idx_hr_employee_department (department_id)`,
`idx_hr_employee_job (job_id)`. Department/job filters and the default name ordering use these
indexes directly. Name text search uses `ilike`: a prefix term (`"ali%"`) is served by the
`text_pattern_ops` btree `idx_hr_employee_name_pattern`; a substring term (`"%ali%"`) falls back to
a filtered scan, which at ≤ 2,000 company-scoped rows still returns well under the 500 ms budget
(no trigram extension is introduced — Principle VII). The target is therefore met for all three
filter shapes named in PERF-001.

**Rationale**: matches the `account` invoice-list approach; no new infra.

## D7 — New web view types (Kanban, Calendar) + org-chart widget

**Decision**:
- `web/static/views/kanban.js`: `render(container, { model, groupBy, cardFields, hash })` — calls
  `fields_get` + `search_read`, groups rows by `groupBy` value, renders columns of cards; card click
  → form route; drag OR a per-card "Move to…" menu (keyboard path) issues the move. Stage columns
  come from the caller (e.g. `hr.recruitment.stage` ordered by `sequence`).
- `web/static/views/calendar.js`: `render(container, { model, dateStartField, dateStopField,
  titleField, hash })` — month grid, events from `search_read` in the visible range; event click →
  form. Keyboard: arrow-key day navigation, Enter opens day's events.
- `hr/static/views/org-chart.js`: bespoke — given an `employee_id`, walk `manager_id` up and
  `search([['manager_id','=',id]])` down one level, render an accessible nested `<ul>` with the
  focused node highlighted; each node links to its form.
- `app.js` gains `#/hr/*` and `#/fleet/*` route rows and `_renderHrMenu` / `_renderFleetMenu`
  sidebar functions modelled on `_renderAccountingMenu`; menus imported from `hr/static/hr-menu.js`
  and `fleet/static/fleet-menu.js` (same shape as `ACCOUNTING_MENU`), each section/item gated by
  `App.state` group flags exposed via `/web/core/info` (extended to return the caller's HR/Fleet
  group names).

**Rationale**: `list.js`/`form.js` are already generic metadata-driven modules; Kanban and Calendar
extend that family. The org chart is inherently HR-shaped (manager relation) so it stays in `hr`,
exactly as Odoo ships it in `hr_org_chart` rather than `web`.

**Alternatives rejected**: a full client-side view-type registry / arch parser (Odoo's approach) —
far more than this SPA needs; a third-party calendar/kanban library — CSP/no-bundler constraint and
Principle VII.

## D8 — Cron-style time advancement without a scheduler

**Decision**: `run_contract_expiry`, `run_leave_accrual`, `run_fleet_contract_expiry` are idempotent
service classmethods (guarded by a stored `last_*_date` or a `state`/`date` predicate) exposed at
`POST /hr/cron/contract-expiry`, `POST /hr/cron/leave-accrual`, `POST /fleet/cron/contract-expiry`
(auth `session`, `HR Administrator` / `Fleet Manager` only). Correctness never depends on them
running: list/search/read derive `expired` and the alert window on the fly; the endpoints only
persist the derived state so `search([('state','=','expired')])` and reports agree.

**Rationale**: dodoo has no scheduler; adding one is a process-model and dependency change
unjustified for three nightly flips. An external timer (system cron / CI job / manual) can hit the
endpoints.

**Alternatives rejected**: APScheduler / a background task (new dependency, Principle VII; changes
the single-process model); pure compute-on-read (breaks stored-state queries and the FR-066 audit
trail for the flip).

## D9 — Observability (FR-066, Principle IX)

**Decision**: each transition/approval method emits `_log.info("<event>", extra={"model":…,
"record_id":…, "actor_uid":…, "event":…, "from":…, "to":…, "company_id":…})`. `correlation_id` is
attached by `CorrelationMiddleware`'s log-record factory. From-state-precondition rejections
(FR-067a) log at `warning` with `event="<x>_state_conflict"`. **No** field values, feedback text,
candidate details, bank/ID numbers, or wages appear in `extra` (SEC-006).

**Rationale**: identical to `account.move.action_post`'s logging shape.

## OWASP Top 10 review (SEC-005)

| Risk | Exposure in this feature | Mitigation |
|------|--------------------------|------------|
| A01 Broken Access Control | cross-employee PII read; approving/refusing another team's leave; self-approval; converting an applicant without recruiter rights; a driver editing fleet config | `ir.rule` per group + company (D4); sensitive-field drop in `hr.employee.read`; approver-set resolution rejects the requester (ADR-025); every REST action re-checks group + relationship server-side (SEC-004); deny-by-default rule on sensitive models (D4 gap fix) |
| A02 Cryptographic Failures | none new (no secrets stored; passwords stay in `res.users`) | employee↔user link stores only `user_id`; no credential handling added |
| A03 Injection | free-text feedback, candidate name/email/phone, service notes, seed data, search terms | ORM uses bound params everywhere (SQLAlchemy `text(:param)` / Core); no f-string SQL with user data; SPA renders via `textContent` (no `innerHTML` for data); domain filters parsed as JSON lists, never `eval` |
| A04 Insecure Design | approval-workflow escalation / step-skipping; contract "≤1 running" bypass; idempotency of applicant→employee | explicit transition tables with from-state guard (ADR-024/025/026/027); one-running-contract guard query; `create_employee` keyed on `applicant.employee_id` |
| A05 Security Misconfiguration | new REST routes defaulting to `auth="public"` | every mutation route declared `auth="session"`; cron routes additionally gated to Administrator/Fleet Manager |
| A06 Vulnerable Components | none — zero new dependencies | — |
| A07 Auth failures | none new — reuses `SessionManager` / `X-Session-Token` | — |
| A08 Data Integrity | `ir_model_sync` / seed re-runs on upgrade | all seeds idempotent (`ON CONFLICT DO NOTHING`, count-guards) like `base_data`/`account_data` |
| A09 Logging failures | missing audit for a transition; PII leakage into logs | FR-066 log on every transition + FR-067a conflict; SEC-006 forbids payloads in `extra`; correlation ID propagated |
| A10 SSRF | none — no outbound requests | — |

**Threat-model note for the ADRs**: the four ADRs each carry a one-line threat note (approval
bypass / balance drift / feedback leak / stale alert) and its guard, per Constitution III.

## Reused precedents (no new decision needed)

- Seeding pattern, idempotency guards, `post_install` hook → `base_data.py`, `account_data.py`.
- Additive FK columns via DDL when avoiding a cross-addon model dependency →
  `localization/data/seed.py::_COMPANY_FK_COLUMNS`, `account_data.py::_PARTNER_FK_COLUMNS`
  (used here only if a `fleet`→`hr` column ever needs to avoid the import; currently `fleet` may
  import `hr` freely since it depends on it).
- State machine + `super().write` immutability guard + structured logging → `account.move`.
- Group-name membership check → `res.config.settings.is_admin`, `base/http/core_info`.
- Static mount + `@route` + SPA lazy view import + cache-bust `CLIENT_BUILD` → `account/http`,
  `web/static/app.js`.
- Test layout (`tests/<addon>/`, real PG, `RouteRegistry.reset()`) → `tests/accounting/`,
  `tests/localization/`, `tests/integration/test_access_rules.py`.
