# Contract: Referrals

Depends on Recruitment (an `hr.applicant` is created for every referral).

## JSON-RPC (`execute_kw`)

| Model | Method | Args / kwargs | Returns | Notes |
|-------|--------|---------------|---------|-------|
| hr.referral | read/search/search_read | standard | `uid` injected → `referrer_id.user_id = uid` rule for `HR Employee` | `status` derived from `applicant_id` |
| hr.referral | `get_my_referrals` | — (uid from context) | `[{id, candidate_name, job_id, status}]` | referrer's own list (FR-048) |
| hr.referral | `get_referrer_stats` | kwargs `{referrer_id:int}` | `{total:int, hired:int}` | FR-049 |
| hr.job | search/search_read | `[["is_published","=",true]]` | | referral target set |

## REST routes

### `POST /hr/referral/submit`
Body: `{ "job_id": int, "candidate_name": str, "candidate_email": str|null, "candidate_phone": str|null }`.
- Referrer = the `hr.employee` of the authenticated user (`hr.employee.resolve_current`); if none →
  `referral_no_employee`.
- `job_id` must be `is_published` → else `referral_job_unpublished` (FR-050).
- Creates `hr.referral` + a linked `hr.applicant` (`source_id` = the `is_referral` source,
  `referral_id` set, `stage_id` = lowest sequence, `company_id` = job's company).
- Success: `{ "result": { "referral_id": int, "applicant_id": int } }`. Logs `referral_submit`.

## Validation model

```
ReferralSubmit: job_id:int; candidate_name:str(1..128); candidate_email:EmailStr|None;
                candidate_phone:str(0..64)|None
```

## Derived `status`
- `applicant_id.refused` → `"refused"`
- `applicant_id.employee_id` set → `"hired"` (counts toward `get_referrer_stats.hired`)
- else → `applicant_id.stage_id.name`

## Error codes
`referral_job_unpublished`, `referral_no_employee`.
