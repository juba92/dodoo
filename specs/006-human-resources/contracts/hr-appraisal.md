# Contract: Appraisals

## JSON-RPC (`execute_kw`)

| Model | Method | Args / kwargs | Returns | Notes |
|-------|--------|---------------|---------|-------|
| hr.appraisal.template | create/write/read/search | standard | | nullable company_id; Administrator write |
| hr.appraisal.feedback.section | create/write/read/search | standard | | child of template |
| hr.appraisal | read/search/search_read | standard | | `uid` injected → owner OR manager OR officer rule |
| hr.appraisal | `get_history` | kwargs `{employee_id:int}` | `[{id, date_close, state}]` | FR-044, order `date_close desc` |
| hr.appraisal.feedback | read/search_read | standard | opposite side sees only `is_visible=true` rows | FR-042 enforced in model layer |
| hr.appraisal.feedback | write | `{content, is_visible}` | | only the owning side may write its rows |

## REST routes

### `POST /hr/appraisal/launch`
Body: `{ "employee_id": int, "template_id": int }`.
- AuthZ: `HR Officer`+ or the employee's manager.
- Creates the appraisal (`state="new"`) and, for each template section, two
  `hr.appraisal.feedback` rows (`side="employee"`, `side="manager"`).
- Success: `{ "result": { "appraisal_id": int } }`. Logs `appraisal_launch`.

### `POST /hr/appraisal/{appraisal_id}/set-state`
Body: `{ "state": "pending_confirmation|confirmed|done|cancelled", "expected_state": "<state>|null" }`.
- Legal moves: `new→pending_confirmation→confirmed→done`; `*→cancelled` from any non-`done`.
- Illegal → `appraisal_transition_invalid`; stale → `appraisal_state_conflict` (FR-067a).
- On `→done`: sets `date_close=today` and
  `employee.next_appraisal_date = today + resolved_frequency_months`
  (employee → department → template).
- Success: `{ "result": { "id": appraisal_id, "state": "<new>", "next_appraisal_date": "<date|null>" } }`.
  Logs `appraisal_state`.

## Validation models

```
AppraisalTemplateCreate: name:str; default_frequency_months:int(ge=1,le=60)=12; company_id:int|None
FeedbackSectionCreate:   template_id:int; title:str(1..128); prompt:str|None; sequence:int(ge=0)=10
AppraisalLaunch:         employee_id:int; template_id:int
AppraisalSetState:       state:Literal['pending_confirmation','confirmed','done','cancelled'];
                         expected_state:Literal['new','pending_confirmation','confirmed']|None
FeedbackWrite:           content:str|None; is_visible:bool
```

## Error codes
`appraisal_transition_invalid`, `appraisal_state_conflict`, `appraisal_not_authorized`,
`feedback_wrong_side` (a caller writing the other side's feedback row).
