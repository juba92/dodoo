"""``hr.appraisal`` — a periodic appraisal cycle (ADR-026, FR-040…FR-045)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.hr._audit import log_conflict, log_transition
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Date, Integer, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STATE = [
    ("new", "New"),
    ("pending_confirmation", "Pending Confirmation"),
    ("confirmed", "Confirmed"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
]

_TRANSITIONS: dict[str, set[str]] = {
    "new": {"pending_confirmation", "cancelled"},
    "pending_confirmation": {"confirmed", "cancelled"},
    "confirmed": {"done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


class HrAppraisal(BaseModel):
    _name = "hr.appraisal"

    employee_id = Many2one("hr.employee", required=True)
    manager_id = Many2one("hr.employee")
    company_id = Many2one("res.company", required=True)
    template_id = Many2one("hr.appraisal.template")
    state = Selection(STATE, default="new")
    date_close = Date()
    frequency_months = Integer()

    # ------------------------------------------------------------------ launch
    @classmethod
    async def action_launch(
        cls,
        env: Environment,
        employee_id: int,
        template_id: int,
        uid: int | None = None,
    ) -> dict[str, Any]:
        async with env.dml_conn() as conn:
            emp = await conn.execute(
                text(
                    "SELECT company_id, manager_id FROM hr_employee WHERE id = :i"
                ),
                {"i": employee_id},
            )
            e = emp.fetchone()
            if not e:
                raise DodooError("employee_not_found")
            sections = await conn.execute(
                text(
                    "SELECT title, prompt FROM hr_appraisal_feedback_section "
                    "WHERE template_id = :t ORDER BY sequence, id"
                ),
                {"t": template_id},
            )
            section_rows = sections.fetchall()

        manager_id = e[1]
        appraisal_id = await super().create(
            env,
            {
                "employee_id": employee_id,
                "manager_id": manager_id,
                "company_id": e[0],
                "template_id": template_id,
                "state": "new",
            },
        )
        from dodoo.addons.hr.models.hr_appraisal_feedback import HrAppraisalFeedback

        for title, _prompt in section_rows:
            for side in ("employee", "manager"):
                await HrAppraisalFeedback.create(
                    env,
                    {
                        "appraisal_id": appraisal_id,
                        "side": side,
                        "section_title": title,
                        "is_visible": False,
                    },
                )
        log_transition(
            _log,
            model=cls._name,
            record_id=appraisal_id,
            event="appraisal_launch",
            to="new",
            actor_uid=uid,
            company_id=e[0],
        )
        return {"appraisal_id": appraisal_id}

    # ------------------------------------------------------------------ state
    @classmethod
    async def action_set_state(
        cls,
        env: Environment,
        ids: list[int],
        target: str,
        uid: int | None = None,
        expected_state: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for aid in ids:
            rows = await super().read(
                env, [aid], ["state", "employee_id", "company_id", "template_id"]
            )
            if not rows:
                raise DodooError("appraisal_not_found")
            rec = rows[0]
            current = rec["state"]
            if expected_state is not None and expected_state != current:
                log_conflict(
                    _log,
                    model=cls._name,
                    record_id=aid,
                    event="appraisal_state_conflict",
                    expected=expected_state,
                    actual=current,
                    actor_uid=uid,
                )
                raise DodooError("appraisal_state_conflict")
            if target == current:
                continue
            if target not in _TRANSITIONS.get(current, set()):
                raise DodooError("appraisal_transition_invalid")

            vals: dict[str, Any] = {"state": target}
            next_date = None
            if target == "done":
                today = datetime.date.today()
                freq = await cls._resolve_frequency(
                    env, rec["employee_id"], rec["template_id"]
                )
                next_date = _add_months(today, freq)
                vals["date_close"] = today
                vals["frequency_months"] = freq
                async with env.dml_conn() as conn:
                    await conn.execute(
                        text(
                            "UPDATE hr_employee SET next_appraisal_date = :d, "
                            "write_date = now() WHERE id = :e"
                        ),
                        {"d": next_date, "e": rec["employee_id"]},
                    )
                    await conn.commit()

            await super().write(env, [aid], vals)
            log_transition(
                _log,
                model=cls._name,
                record_id=aid,
                event="appraisal_state",
                frm=current,
                to=target,
                actor_uid=uid,
                company_id=rec["company_id"],
            )
            result = {
                "id": aid,
                "state": target,
                "next_appraisal_date": next_date.isoformat() if next_date else None,
            }
        return result

    # ------------------------------------------------------------------ helpers
    @classmethod
    async def _resolve_frequency(
        cls, env: Environment, employee_id: int, template_id: int | None
    ) -> int:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT e.appraisal_frequency_months, d.appraisal_frequency_months "
                    "FROM hr_employee e "
                    "LEFT JOIN hr_department d ON d.id = e.department_id "
                    "WHERE e.id = :i"
                ),
                {"i": employee_id},
            )
            r = row.fetchone()
            if r and r[0]:
                return int(r[0])
            if r and r[1]:
                return int(r[1])
            if template_id:
                trow = await conn.execute(
                    text(
                        "SELECT default_frequency_months FROM hr_appraisal_template "
                        "WHERE id = :t"
                    ),
                    {"t": template_id},
                )
                tr = trow.fetchone()
                if tr and tr[0]:
                    return int(tr[0])
        return 12

    @classmethod
    async def _resolve_appraiser(
        cls, env: Environment, employee_id: int
    ) -> int | None:
        """The manager's user, or an HR Officer when there is no manager / self-appraisal."""
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT e.user_id, m.user_id FROM hr_employee e "
                    "LEFT JOIN hr_employee m ON m.id = e.manager_id WHERE e.id = :i"
                ),
                {"i": employee_id},
            )
            r = row.fetchone()
            emp_uid = r[0] if r else None
            mgr_uid = r[1] if r else None
            if mgr_uid and mgr_uid != emp_uid:
                return mgr_uid
            officer = await conn.execute(
                text(
                    "SELECT r.user_id FROM res_users_groups_rel r "
                    "JOIN res_groups g ON g.id = r.group_id "
                    "WHERE g.name IN ('HR Officer', 'HR Administrator') "
                    "AND r.user_id <> COALESCE(:emp, -1) LIMIT 1"
                ),
                {"emp": emp_uid},
            )
            o = officer.fetchone()
            return o[0] if o else None

    @classmethod
    async def get_history(
        cls, env: Environment, employee_id: int
    ) -> list[dict[str, Any]]:
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, date_close, state FROM hr_appraisal "
                    "WHERE employee_id = :e "
                    "ORDER BY COALESCE(date_close, '9999-12-31') DESC, id DESC"
                ),
                {"e": employee_id},
            )
            return [dict(r._mapping) for r in rows]


def _add_months(d: datetime.date, months: int) -> datetime.date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    day = min(
        d.day,
        [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
         31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1],
    )
    return datetime.date(year, month, day)
