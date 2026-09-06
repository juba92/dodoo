"""``hr.applicant`` — a candidate moving through the recruitment pipeline (US3).

"Hired" is derived from ``stage_id.is_hired_stage``; there is no separate applicant state
machine beyond ``stage`` + ``refused``. ``create_employee`` is idempotent (FR-038).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.hr._audit import log_conflict, log_transition
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Many2many, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class HrApplicant(BaseModel):
    _name = "hr.applicant"

    partner_name = Char(size=128, required=True)
    email_from = Char(size=256)
    partner_phone = Char(size=64)
    job_id = Many2one("hr.job", required=True)
    department_id = Many2one("hr.department")
    company_id = Many2one("res.company", required=True)
    source_id = Many2one("hr.recruitment.source")
    stage_id = Many2one("hr.recruitment.stage", required=True)
    interviewer_ids = Many2many(
        "res.users",
        relation_table="hr_applicant_interviewer_rel",
        column1="applicant_id",
        column2="user_id",
    )
    refused = Boolean(default=False)
    refuse_reason_id = Many2one("hr.applicant.refuse.reason")
    employee_id = Many2one("hr.employee")
    referral_id = Many2one("hr.referral")

    # ------------------------------------------------------------------ create
    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        vals = dict(vals)
        if not vals.get("department_id") and vals.get("job_id"):
            async with env.dml_conn() as conn:
                row = await conn.execute(
                    text("SELECT department_id, company_id FROM hr_job WHERE id = :j"),
                    {"j": vals["job_id"]},
                )
                r = row.fetchone()
                if r:
                    vals.setdefault("department_id", r[0])
                    vals.setdefault("company_id", r[1])
        if not vals.get("stage_id"):
            async with env.dml_conn() as conn:
                row = await conn.execute(
                    text(
                        "SELECT id FROM hr_recruitment_stage "
                        "ORDER BY sequence, id LIMIT 1"
                    )
                )
                r = row.fetchone()
                if not r:
                    raise DodooError("recruitment_no_stage")
                vals["stage_id"] = r[0]
        return await super().create(env, vals)

    # ------------------------------------------------------------------ stage
    @classmethod
    async def action_set_stage(
        cls,
        env: Environment,
        ids: list[int],
        stage_id: int,
        uid: int | None = None,
        expected_stage_id: int | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for aid in ids:
            rows = await super().read(env, [aid], ["stage_id", "company_id"])
            if not rows:
                raise DodooError("applicant_not_found")
            current = rows[0]["stage_id"]
            if expected_stage_id is not None and expected_stage_id != current:
                log_conflict(
                    _log,
                    model=cls._name,
                    record_id=aid,
                    event="applicant_stage_conflict",
                    expected=str(expected_stage_id),
                    actual=str(current),
                    actor_uid=uid,
                )
                raise DodooError("applicant_stage_conflict")
            await super().write(env, [aid], {"stage_id": stage_id})
            hired = await cls._is_hired_stage(env, stage_id)
            log_transition(
                _log,
                model=cls._name,
                record_id=aid,
                event="applicant_stage",
                frm=str(current),
                to=str(stage_id),
                actor_uid=uid,
                company_id=rows[0]["company_id"],
            )
            result = {"id": aid, "stage_id": stage_id, "hired": hired}
        return result

    @classmethod
    async def action_refuse(
        cls, env: Environment, ids: list[int], uid: int | None, reason_id: int
    ) -> dict[str, Any]:
        for aid in ids:
            rows = await super().read(env, [aid], ["company_id"])
            if not rows:
                raise DodooError("applicant_not_found")
            await super().write(
                env, [aid], {"refused": True, "refuse_reason_id": reason_id}
            )
            log_transition(
                _log,
                model=cls._name,
                record_id=aid,
                event="applicant_refuse",
                to="refused",
                actor_uid=uid,
                company_id=rows[0]["company_id"],
            )
        return {"ok": True}

    # ------------------------------------------------------------------ hire
    @classmethod
    async def create_employee(
        cls, env: Environment, applicant_id: int, uid: int | None = None
    ) -> dict[str, Any]:
        rows = await super().read(
            env,
            [applicant_id],
            [
                "partner_name",
                "email_from",
                "partner_phone",
                "job_id",
                "department_id",
                "company_id",
                "employee_id",
            ],
        )
        if not rows:
            raise DodooError("applicant_not_found")
        rec = rows[0]
        if rec.get("employee_id"):
            return {"employee_id": rec["employee_id"], "created": False}

        from dodoo.addons.hr.models.hr_employee import HrEmployee

        emp_id = await HrEmployee.create(
            env,
            {
                "name": rec["partner_name"],
                "work_email": rec.get("email_from"),
                "work_phone": rec.get("partner_phone"),
                "job_id": rec.get("job_id"),
                "department_id": rec.get("department_id"),
                "company_id": rec["company_id"],
                # no user_id — never auto-provision a login (clarify pass 2)
            },
        )
        await super().write(env, [applicant_id], {"employee_id": emp_id})
        log_transition(
            _log,
            model=cls._name,
            record_id=applicant_id,
            event="applicant_hired",
            to="hired",
            actor_uid=uid,
            company_id=rec["company_id"],
            employee_id=emp_id,
        )
        return {"employee_id": emp_id, "created": True}

    # ------------------------------------------------------------------ pipeline
    @classmethod
    async def get_pipeline(cls, env: Environment, job_id: int) -> dict[str, Any]:
        async with env.dml_conn() as conn:
            stages = await conn.execute(
                text(
                    "SELECT id, name, sequence, is_hired_stage FROM hr_recruitment_stage "
                    "ORDER BY sequence, id"
                )
            )
            stage_list = [dict(r._mapping) for r in stages]
            apps = await conn.execute(
                text(
                    "SELECT id, partner_name, email_from, partner_phone, stage_id "
                    "FROM hr_applicant WHERE job_id = :j AND refused = FALSE "
                    "ORDER BY id"
                ),
                {"j": job_id},
            )
            cards: dict[str, list[dict[str, Any]]] = {
                str(s["id"]): [] for s in stage_list
            }
            for a in apps:
                d = dict(a._mapping)
                cards.setdefault(str(d["stage_id"]), []).append(d)
        return {"stages": stage_list, "cards": cards}

    @classmethod
    async def _is_hired_stage(cls, env: Environment, stage_id: int) -> bool:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT is_hired_stage FROM hr_recruitment_stage WHERE id = :i"),
                {"i": stage_id},
            )
            r = row.fetchone()
        return bool(r and r[0])
