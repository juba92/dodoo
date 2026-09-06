# Contract: Time Off

## JSON-RPC (`execute_kw`)

| Model | Method | Args / kwargs | Returns | Notes |
|-------|--------|---------------|---------|-------|
| hr.leave.type | create/write/read/search | standard | | nullable company_id; Administrator write |
| hr.leave.allocation | create/write/read/search | standard | | accrual fields required when mode=accrual |
| hr.leave | create | `[vals]` | id | computes duration; overlap + zero-day + balance guards run here |
| hr.leave | read/search/search_read | standard | | `uid` injected → owner/manager/officer rules |
| hr.leave | `get_balance` | kwargs `{employee_id:int, leave_type_id:int}` | `{allocated, taken, pending, available}` | PERF-002 path |
| hr.leave | `get_duration_preview` | kwargs `{employee_id, date_from, date_to, unit}` | `{units: float}` | UI helper; no write |
| resource.calendar / .attendance | read/search | standard | | one per company; Administrator write |
| hr.public.holiday | create/write/read/search | standard | | nullable company_id; Administrator write |

## REST routes

### `POST /hr/leave/{leave_id}/approve`
Body: `{ "expected_state": "to_approve|second_approval" }` (optional).
- Resolves the approver set (ADR-025): the `res.users` linked to `employee.manager_id`; if none or
  the caller is the requester with no other approver → escalates to any `HR Officer` in the
  employee's company. Caller not in the set → `leave_not_authorized`.
- Advances exactly one step: `to_approve → approved` (modes `manager`/`hr`), or
  `to_approve → second_approval → approved` (mode `both`, two distinct users).
- Stale state → `leave_state_conflict`. Insufficient balance (re-checked) → `leave_insufficient_balance`.
- Success: `{ "result": { "id": leave_id, "state": "<new>", "step": 1|2 } }`. Logs `leave_approve`.

### `POST /hr/leave/{leave_id}/refuse`
Body: `{ "reason": str(0..256), "expected_state": "to_approve|second_approval|approved" }`.
- `→ refused`; if previous state was `approved`, the consumed balance is released (taken recomputed).
- AuthZ: same approver set, or `HR Officer`+. Logs `leave_refuse`.

### `POST /hr/cron/leave-accrual`
Body: `{}`. AuthZ: `HR Administrator`. Idempotent — for each `mode='accrual'` allocation, adds
`floor(periods since last_accrual_date) * accrual_rate` capped at `accrual_max`, updates
`last_accrual_date`. Returns `{ "result": { "updated": <count>, "units_added": <float> } }`.

## Validation models

```
LeaveTypeCreate:       name:str; company_id:int|None; request_unit:Literal['day','hour']='day';
                       is_paid:bool=True; allocation_required:bool=True; allow_negative:bool=False;
                       approval_mode:Literal['no_validation','manager','hr','both']='manager'
AllocationCreate:      employee_id:int; leave_type_id:int; company_id:int;
                       mode:Literal['regular','accrual']='regular'; number_of_units:float(ge=0)=0;
                       accrual_rate:float(ge=0)=0; accrual_period:Literal['day','week','month']|None;
                       accrual_max:float(ge=0)|None; date_from:date|None; date_to:date|None
                       @model_validator: accrual_* required iff mode=='accrual'
LeaveCreate:           employee_id:int; leave_type_id:int; company_id:int;
                       date_from:datetime; date_to:datetime
                       @model_validator: date_to > date_from
LeaveApprove:          expected_state:Literal['to_approve','second_approval']|None
LeaveRefuse:           reason:str(0..256)=''; expected_state:Literal[...]|None
PublicHolidayCreate:   name:str; date_from:date; date_to:date; company_id:int|None
                       @model_validator: date_to >= date_from
```

## Error codes
`leave_zero_days`, `leave_overlap`, `leave_insufficient_balance`, `leave_not_authorized`,
`leave_self_approval` (surfaced only if escalation also fails — no officer exists),
`leave_state_conflict`, `accrual_config_invalid`.
