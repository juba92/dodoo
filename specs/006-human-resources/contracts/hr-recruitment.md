# Contract: Recruitment

## JSON-RPC (`execute_kw`)

| Model | Method | Args / kwargs | Returns | Notes |
|-------|--------|---------------|---------|-------|
| hr.recruitment.stage | create/write/read/search | standard | | nullable company_id; Officer+ write; `is_hired_stage` |
| hr.recruitment.source | create/write/read/search | standard | | one row has `is_referral=True` |
| hr.applicant.refuse.reason | create/write/read/search | standard | | global |
| hr.applicant | create/write/read/search/search_read | standard | | `department_id` defaulted from `job_id`; refused rows excluded from pipeline queries by callers passing `[["refused","=",false]]` |
| hr.applicant | `get_pipeline` | kwargs `{job_id:int}` | `{stages:[{id,name,sequence}], cards:{stage_id:[{id,partner_name,email_from,...}]}}` | PERF-003 single grouped query |
| hr.job | write | `{is_published: bool}` | | publish flag (FR-032) |

## REST routes

### `POST /hr/applicant/{applicant_id}/set-stage`
Body: `{ "stage_id": int, "expected_stage_id": int|null }`.
- AuthZ: `HR Officer`+ for the applicant's company (recruiter role).
- `expected_stage_id` mismatch → `applicant_stage_conflict` (FR-067a).
- Success: `{ "result": { "id": applicant_id, "stage_id": <new>, "hired": bool } }`. Logs
  `applicant_stage`. `hired` = new stage `is_hired_stage`.

### `POST /hr/applicant/{applicant_id}/refuse`
Body: `{ "refuse_reason_id": int }`.
- Sets `refused=True`, stores reason; applicant leaves the active pipeline (data retained).
- Success: `{ "result": { "id": applicant_id, "refused": true } }`. Logs `applicant_refuse`.

### `POST /hr/applicant/{applicant_id}/create-employee`
Body: `{}`.
- Idempotent: if `employee_id` already set → returns it. Else creates `hr.employee`
  (`name`, `work_email`, `work_phone`, `job_id`, `department_id`, `company_id`; **no `user_id`**),
  links `applicant.employee_id`.
- AuthZ: `HR Officer`+.
- Success: `{ "result": { "employee_id": int, "created": bool } }`. Logs `applicant_hired`.

## Validation models

```
ApplicantCreate:   partner_name:str(1..128); email_from:EmailStr|None; partner_phone:str|None;
                   job_id:int; department_id:int|None; company_id:int; source_id:int|None;
                   stage_id:int|None; interviewer_ids:list[int]=[]
ApplicantSetStage: stage_id:int; expected_stage_id:int|None
ApplicantRefuse:   refuse_reason_id:int
StageCreate:       name:str; sequence:int(ge=0)=10; is_hired_stage:bool=False; company_id:int|None
SourceCreate:      name:str; is_referral:bool=False; company_id:int|None
```

## Error codes
`applicant_stage_conflict`, `applicant_not_authorized`, `applicant_job_missing`,
`applicant_already_hired` (never raised — idempotent path returns existing employee instead).
