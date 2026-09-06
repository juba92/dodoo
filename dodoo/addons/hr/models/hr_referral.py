"""``hr.referral`` — an employee's referral of a candidate to a published job (US5).

Submitting a referral creates a linked ``hr.applicant`` with the employee-referral source
(FR-047). ``status`` is derived from the applicant's stage / refused / hired state (FR-048).
A referral cannot be created against an unpublished job (FR-050).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.hr._audit import log_transition
from dodoo.core.context import get_uid
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class HrReferral(BaseModel):
    _name = "hr.referral"

    referrer_id = Many2one("hr.employee", required=True)
    job_id = Many2one("hr.job", required=True)
    company_id = Many2one("res.company", required=True)
    candidate_name = Char(size=128, required=True)
    candidate_email = Char(size=256)
    candidate_phone = Char(size=64)
    applicant_id = Many2one("hr.applicant")

    # ------------------------------------------------------------------ submit
    @classmethod
    async def action_submit(
        cls, env: Environment, vals: dict[str, Any], uid: int | None = None
    ) -> dict[str, Any]:
        uid = uid or get_uid()
        async with env.dml_conn() as conn:
            emp = await conn.execute(
                text(
                    "SELECT id, company_id FROM hr_employee "
                    "WHERE user_id = :u AND active = TRUE ORDER BY id LIMIT 1"
                ),
                {"u": uid},
            )
            erow = emp.fetchone()
            if not erow:
                raise DodooError("referral_no_employee")
            referrer_id, referrer_company = erow[0], erow[1]

            job = await conn.execute(
                text(
                    "SELECT is_published, company_id, department_id FROM hr_job "
                    "WHERE id = :j"
                ),
                {"j": vals["job_id"]},
            )
            jrow = job.fetchone()
            if not jrow:
                raise DodooError("referral_job_not_found")
            if not jrow[0]:
                raise DodooError("referral_job_unpublished")

            src = await conn.execute(
                text(
                    "SELECT id FROM hr_recruitment_source WHERE is_referral = TRUE "
                    "ORDER BY id LIMIT 1"
                )
            )
            srow = src.fetchone()
            source_id = srow[0] if srow else None
            company_id = jrow[1] or referrer_company

        ref_id = await super().create(
            env,
            {
                "referrer_id": referrer_id,
                "job_id": vals["job_id"],
                "company_id": company_id,
                "candidate_name": vals["candidate_name"],
                "candidate_email": vals.get("candidate_email"),
                "candidate_phone": vals.get("candidate_phone"),
            },
        )

        from dodoo.addons.hr.models.hr_applicant import HrApplicant

        applicant_id = await HrApplicant.create(
            env,
            {
                "partner_name": vals["candidate_name"],
                "email_from": vals.get("candidate_email"),
                "partner_phone": vals.get("candidate_phone"),
                "job_id": vals["job_id"],
                "company_id": company_id,
                "source_id": source_id,
                "referral_id": ref_id,
            },
        )
        await super().write(env, [ref_id], {"applicant_id": applicant_id})
        log_transition(
            _log,
            model=cls._name,
            record_id=ref_id,
            event="referral_submit",
            to="submitted",
            actor_uid=uid,
            company_id=company_id,
            applicant_id=applicant_id,
        )
        return {"referral_id": ref_id, "applicant_id": applicant_id}

    # ------------------------------------------------------------------ status
    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        rows = await super().read(env, ids, fields)
        want = fields is None or "status" in fields
        if not want or not rows:
            return rows
        app_ids = [r["applicant_id"] for r in rows if r.get("applicant_id")]
        status_by_app = await cls._applicant_status(env, app_ids)
        for r in rows:
            r["status"] = status_by_app.get(r.get("applicant_id"), "submitted")
        return rows

    @classmethod
    async def _applicant_status(
        cls, env: Environment, app_ids: list[int]
    ) -> dict[int, str]:
        if not app_ids:
            return {}
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT a.id, a.refused, a.employee_id, s.name "
                    "FROM hr_applicant a "
                    "LEFT JOIN hr_recruitment_stage s ON s.id = a.stage_id "
                    "WHERE a.id = ANY(:ids)"
                ),
                {"ids": app_ids},
            )
            out: dict[int, str] = {}
            for r in rows:
                if r[1]:
                    out[r[0]] = "refused"
                elif r[2]:
                    out[r[0]] = "hired"
                else:
                    out[r[0]] = r[3] or "submitted"
        return out

    # ------------------------------------------------------------------ views
    @classmethod
    async def get_my_referrals(cls, env: Environment) -> list[dict[str, Any]]:
        uid = get_uid()
        if not uid:
            return []
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT r.id, r.candidate_name, r.job_id, r.applicant_id "
                    "FROM hr_referral r "
                    "JOIN hr_employee e ON e.id = r.referrer_id "
                    "WHERE e.user_id = :u ORDER BY r.id DESC"
                ),
                {"u": uid},
            )
            refs = [dict(x._mapping) for x in rows]
        status_by_app = await cls._applicant_status(
            env, [r["applicant_id"] for r in refs if r["applicant_id"]]
        )
        for r in refs:
            r["status"] = status_by_app.get(r["applicant_id"], "submitted")
        return refs

    @classmethod
    async def get_referrer_stats(
        cls, env: Environment, referrer_id: int
    ) -> dict[str, int]:
        async with env.dml_conn() as conn:
            total = await conn.execute(
                text("SELECT COUNT(*) FROM hr_referral WHERE referrer_id = :r"),
                {"r": referrer_id},
            )
            hired = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM hr_referral r "
                    "JOIN hr_applicant a ON a.id = r.applicant_id "
                    "WHERE r.referrer_id = :r AND a.employee_id IS NOT NULL"
                ),
                {"r": referrer_id},
            )
        return {"total": total.scalar_one(), "hired": hired.scalar_one()}
