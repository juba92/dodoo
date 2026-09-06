# Contract: Employees, Departments, Jobs, Contracts, Skills

Two transports (research.md D2): JSON-RPC `execute_kw` for CRUD + read-side helpers, REST
`@route` for verbs. All REST routes `auth="session"`; bodies validated by `hr/validators.py`
(Pydantic v2, `extra="forbid"`). Errors: `{"error": "<code>"}` + HTTP 400; RPC errors use the
existing `_err` envelope (`DodooError` → -32602, `AccessError` → -32000).

## JSON-RPC (`service:"object", method:"execute_kw"`, args `[model, method, args, kwargs]`)

| Model | Method | Args / kwargs | Returns | Notes |
|-------|--------|---------------|---------|-------|
| hr.department | create/write/read/search/search_read/unlink | standard | | cycle rejected on create/write |
| hr.job | create/write/read/search/search_read | standard | `no_of_employees` present in read | |
| hr.employee | create/write/read/search/search_read/unlink | standard; `read` honours sensitive-field drop | | `uid` auto-injected for search/search_read |
| hr.employee | `get_org_chart` | kwargs `{employee_id:int}` | `{manager_chain:[{id,name,job_title}], reports:[{id,name,job_title}]}` | manager chain root→employee; reports = direct only |
| hr.employee | `resolve_current` | — (uid from context) | `{employee_id:int|null}` | current user's employee (FR-005) |
| hr.employee.category | create/write/read/search | standard | | global |
| hr.contract | create/write/read/search/search_read | standard; read/list return `_effective_state` | | one-running guard on `→running` |
| hr.contract | `get_running_contract` | kwargs `{employee_id:int}` | `{contract_id:int|null, ...}` | ADR-024 lookup |
| hr.contract.type | create/write/read/search | standard | | nullable company_id |
| hr.skill.type / hr.skill / hr.skill.level | create/write/read/search | standard | | global catalogs |
| hr.employee.skill | create/write/read/search/unlink | standard | | level-type + duplicate guards |

## REST routes

### `POST /hr/contract/{contract_id}/set-state`
Body: `{ "state": "draft|running|expired|cancelled", "expected_state": "draft|running|expired|cancelled" }`
- `expected_state` optional; when present and ≠ current → `contract_state_conflict` (FR-067a).
- Illegal transition → `contract_transition_invalid`. Second running contract → `contract_running_exists`.
- Success: `{ "result": { "id": contract_id, "state": "<new>" } }`. Logs `contract_state`.
- AuthZ: `HR Officer`+ or the owning employee's manager.

### `POST /hr/cron/contract-expiry`
Body: `{}`. AuthZ: `HR Administrator`. Idempotent. Flips `running` rows with `date_end < today` to
`expired`. Returns `{ "result": { "expired": <count> } }`.

### `GET /hr/employee/{employee_id}/org-chart`
Same payload as the `get_org_chart` RPC (convenience for the widget). AuthZ: any HR group,
company-scoped.

## Validation models (hr/validators.py) — shapes

```
EmployeeCreate:      name:str(1..256); company_id:int; work_email:EmailStr|None;
                     department_id:int|None; job_id:int|None; manager_id:int|None;
                     coach_id:int|None; user_id:int|None; category_ids:list[int]=[]
                     gender:Literal['male','female','other']|None; birthday:date|None
                     marital:Literal['single','married','cohabitant','widower','divorced']|None
                     identification_id/bank_account:str(0..64)|None; home_address:str|None
                     dependant_count:int(ge=0)=0
ContractCreate:      name:str; employee_id:int; company_id:int; contract_type_id:int|None
                     wage:Decimal(ge=0)=0; date_start:date; date_end:date|None;
                     trial_date_end:date|None
                     @model_validator: date_end>=date_start; trial in window
ContractSetState:    state:Literal['draft','running','expired','cancelled'];
                     expected_state:Literal[...]|None
EmployeeSkillCreate: employee_id:int; skill_id:int; skill_level_id:int
DepartmentCreate:    name:str; parent_id:int|None; manager_id:int|None; company_id:int
JobCreate:           name:str; department_id:int|None; company_id:int;
                     expected_employees:int(ge=0)=0; is_published:bool=False
```

Any field not listed for an action → `422 unknown field`.
