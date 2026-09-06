"""``hr.leave`` — a time-off request with a multi-step approval workflow (ADR-025).

Duration is computed set-based against the company ``resource.calendar`` minus public
holidays (FR-025). Balance = allocated − taken − pending (FR-029). Overlap and zero-day
requests are rejected at ``create`` (FR-026/FR-027).
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.hr._audit import log_conflict, log_transition
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Datetime, Float, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STATE = [
    ("to_approve", "To Approve"),
    ("second_approval", "Second Approval"),
    ("approved", "Approved"),
    ("refused", "Refused"),
]

_CONSUMING = ("to_approve", "second_approval", "approved")


class HrLeave(BaseModel):
    _name = "hr.leave"

    employee_id = Many2one("hr.employee", required=True)
    leave_type_id = Many2one("hr.leave.type", required=True)
    company_id = Many2one("res.company", required=True)
    date_from = Datetime(required=True)
    date_to = Datetime(required=True)
    number_of_units = Float(default=0.0, readonly=True)
    state = Selection(STATE, default="to_approve")
    first_approver_id = Many2one("res.users")
    second_approver_id = Many2one("res.users")
    refuse_reason = Char(size=256)

    # ------------------------------------------------------------------ duration
    @classmethod
    async def _leave_duration(
        cls,
        env: Environment,
        company_id: int,
        date_from: Any,
        date_to: Any,
        unit: str,
    ) -> float:
        d0 = _as_date(date_from)
        d1 = _as_date(date_to)
        if d1 < d0:
            return 0.0
        async with env.dml_conn() as conn:
            cal = await conn.execute(
                text(
                    "SELECT id FROM resource_calendar WHERE company_id = :c "
                    "ORDER BY id LIMIT 1"
                ),
                {"c": company_id},
            )
            cal_row = cal.fetchone()
            if not cal_row:
                # No calendar → Monday–Friday, 8h/day fallback.
                rows = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM generate_series(:d0::date, :d1::date, '1 day') AS d "
                        "WHERE EXTRACT(ISODOW FROM d) < 6 "
                        "AND NOT EXISTS (SELECT 1 FROM hr_public_holiday h "
                        "  WHERE (h.company_id = :c OR h.company_id IS NULL) "
                        "  AND d::date BETWEEN h.date_from AND h.date_to)"
                    ),
                    {"d0": d0, "d1": d1, "c": company_id},
                )
                days = rows.scalar_one()
                return float(days if unit == "day" else days * 8)

            cal_id = cal_row[0]
            if unit == "hour":
                rows = await conn.execute(
                    text(
                        "SELECT COALESCE(SUM(a.hour_to - a.hour_from), 0) "
                        "FROM generate_series(:d0::date, :d1::date, '1 day') AS d "
                        "JOIN resource_calendar_attendance a "
                        "  ON a.calendar_id = :cal "
                        "  AND a.dayofweek = (EXTRACT(ISODOW FROM d)::int - 1)::text "
                        "WHERE NOT EXISTS (SELECT 1 FROM hr_public_holiday h "
                        "  WHERE (h.company_id = :c OR h.company_id IS NULL) "
                        "  AND d::date BETWEEN h.date_from AND h.date_to)"
                    ),
                    {"d0": d0, "d1": d1, "cal": cal_id, "c": company_id},
                )
                return float(rows.scalar_one() or 0)
            rows = await conn.execute(
                text(
                    "SELECT COUNT(DISTINCT d::date) "
                    "FROM generate_series(:d0::date, :d1::date, '1 day') AS d "
                    "WHERE EXISTS (SELECT 1 FROM resource_calendar_attendance a "
                    "  WHERE a.calendar_id = :cal "
                    "  AND a.dayofweek = (EXTRACT(ISODOW FROM d)::int - 1)::text) "
                    "AND NOT EXISTS (SELECT 1 FROM hr_public_holiday h "
                    "  WHERE (h.company_id = :c OR h.company_id IS NULL) "
                    "  AND d::date BETWEEN h.date_from AND h.date_to)"
                ),
                {"d0": d0, "d1": d1, "cal": cal_id, "c": company_id},
            )
            return float(rows.scalar_one())

    # ------------------------------------------------------------------ balance
    @classmethod
    async def get_balance(
        cls, env: Environment, employee_id: int, leave_type_id: int
    ) -> dict[str, float]:
        async with env.dml_conn() as conn:
            alloc = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(number_of_units), 0) FROM hr_leave_allocation "
                    "WHERE employee_id = :e AND leave_type_id = :t AND state = 'confirmed'"
                ),
                {"e": employee_id, "t": leave_type_id},
            )
            allocated = float(alloc.scalar_one())
            taken = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(number_of_units), 0) FROM hr_leave "
                    "WHERE employee_id = :e AND leave_type_id = :t AND state = 'approved'"
                ),
                {"e": employee_id, "t": leave_type_id},
            )
            taken_v = float(taken.scalar_one())
            pending = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(number_of_units), 0) FROM hr_leave "
                    "WHERE employee_id = :e AND leave_type_id = :t "
                    "AND state IN ('to_approve', 'second_approval')"
                ),
                {"e": employee_id, "t": leave_type_id},
            )
            pending_v = float(pending.scalar_one())
        return {
            "allocated": allocated,
            "taken": taken_v,
            "pending": pending_v,
            "available": allocated - taken_v - pending_v,
        }

    @classmethod
    async def get_duration_preview(
        cls,
        env: Environment,
        employee_id: int,
        date_from: str,
        date_to: str,
        unit: str = "day",
    ) -> dict[str, float]:
        company_id = await _employee_company(env, employee_id)
        units = await cls._leave_duration(env, company_id, date_from, date_to, unit)
        return {"units": units}

    # ------------------------------------------------------------------ create
    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        employee_id = vals["employee_id"]
        leave_type_id = vals["leave_type_id"]
        company_id = vals.get("company_id") or await _employee_company(env, employee_id)
        vals = {**vals, "company_id": company_id}

        ltype = await _leave_type(env, leave_type_id)
        units = await cls._leave_duration(
            env, company_id, vals["date_from"], vals["date_to"], ltype["request_unit"]
        )
        if units <= 0:
            raise DodooError("leave_zero_days")

        await cls._assert_no_overlap(env, employee_id, vals["date_from"], vals["date_to"], None)

        if ltype["allocation_required"] and not ltype["allow_negative"]:
            bal = await cls.get_balance(env, employee_id, leave_type_id)
            if bal["available"] < units:
                raise DodooError("leave_insufficient_balance")

        vals["number_of_units"] = units
        if ltype["approval_mode"] == "no_validation":
            vals["state"] = "approved"
        new_id = await super().create(env, vals)
        log_transition(
            _log,
            model=cls._name,
            record_id=new_id,
            event="leave_create",
            to=vals.get("state", "to_approve"),
            actor_uid=None,
            company_id=company_id,
        )
        return new_id

    @classmethod
    async def _assert_no_overlap(
        cls,
        env: Environment,
        employee_id: int,
        date_from: Any,
        date_to: Any,
        exclude_id: int | None,
    ) -> None:
        async with env.dml_conn() as conn:
            params: dict[str, Any] = {
                "e": employee_id,
                "f": _as_dt(date_from),
                "t": _as_dt(date_to),
            }
            sql = (
                "SELECT 1 FROM hr_leave "
                "WHERE employee_id = :e AND state <> 'refused' "
                "AND tsrange(date_from, date_to, '[]') && tsrange(:f, :t, '[]')"
            )
            if exclude_id is not None:
                sql += " AND id <> :x"
                params["x"] = exclude_id
            row = await conn.execute(text(sql + " LIMIT 1"), params)
            if row.fetchone():
                raise DodooError("leave_overlap")

    # ------------------------------------------------------------------ approve
    @classmethod
    async def action_approve(
        cls,
        env: Environment,
        ids: list[int],
        uid: int | None,
        expected_state: str | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for lid in ids:
            rows = await super().read(
                env, [lid], ["state", "employee_id", "leave_type_id", "company_id"]
            )
            if not rows:
                raise DodooError("leave_not_found")
            rec = rows[0]
            current = rec["state"]
            if expected_state is not None and expected_state != current:
                log_conflict(
                    _log,
                    model=cls._name,
                    record_id=lid,
                    event="leave_state_conflict",
                    expected=expected_state,
                    actual=current,
                    actor_uid=uid,
                )
                raise DodooError("leave_state_conflict")
            if current not in ("to_approve", "second_approval"):
                raise DodooError("leave_state_conflict")

            approvers = await cls._approver_uids(env, rec["employee_id"], rec["company_id"])
            if uid not in approvers:
                raise DodooError("leave_not_authorized")

            ltype = await _leave_type(env, rec["leave_type_id"])
            if current == "to_approve" and ltype["approval_mode"] == "both":
                nxt, step = "second_approval", 1
                await super().write(env, [lid], {"state": nxt, "first_approver_id": uid})
            else:
                if current == "second_approval" and uid == await cls._first_approver(env, lid):
                    raise DodooError("leave_not_authorized")
                nxt, step = "approved", 2 if current == "second_approval" else 1
                col = "second_approver_id" if current == "second_approval" else "first_approver_id"
                await super().write(env, [lid], {"state": nxt, col: uid})

            log_transition(
                _log,
                model=cls._name,
                record_id=lid,
                event="leave_approve",
                frm=current,
                to=nxt,
                actor_uid=uid,
                company_id=rec["company_id"],
                step=step,
            )
            results.append({"id": lid, "state": nxt, "step": step})
        return results[0] if len(results) == 1 else {"results": results}

    @classmethod
    async def action_refuse(
        cls,
        env: Environment,
        ids: list[int],
        uid: int | None,
        reason: str = "",
        expected_state: str | None = None,
    ) -> dict[str, Any]:
        for lid in ids:
            rows = await super().read(
                env, [lid], ["state", "employee_id", "company_id"]
            )
            if not rows:
                raise DodooError("leave_not_found")
            rec = rows[0]
            current = rec["state"]
            if expected_state is not None and expected_state != current:
                raise DodooError("leave_state_conflict")
            if current == "refused":
                continue
            approvers = await cls._approver_uids(env, rec["employee_id"], rec["company_id"])
            if uid not in approvers:
                raise DodooError("leave_not_authorized")
            await super().write(
                env, [lid], {"state": "refused", "refuse_reason": reason or None}
            )
            log_transition(
                _log,
                model=cls._name,
                record_id=lid,
                event="leave_refuse",
                frm=current,
                to="refused",
                actor_uid=uid,
                company_id=rec["company_id"],
            )
        return {"ok": True}

    # ------------------------------------------------------------------ helpers
    @classmethod
    async def _approver_uids(
        cls, env: Environment, employee_id: int, company_id: int
    ) -> set[int]:
        """Manager's user + every HR Officer in the company; the requester is excluded."""
        async with env.dml_conn() as conn:
            mgr = await conn.execute(
                text(
                    "SELECT m.user_id FROM hr_employee e "
                    "JOIN hr_employee m ON m.id = e.manager_id "
                    "WHERE e.id = :e"
                ),
                {"e": employee_id},
            )
            mrow = mgr.fetchone()
            manager_uid = mrow[0] if mrow else None

            requester = await conn.execute(
                text("SELECT user_id FROM hr_employee WHERE id = :e"), {"e": employee_id}
            )
            rrow = requester.fetchone()
            requester_uid = rrow[0] if rrow else None

            officers = await conn.execute(
                text(
                    "SELECT r.user_id FROM res_users_groups_rel r "
                    "JOIN res_groups g ON g.id = r.group_id "
                    "WHERE g.name IN ('HR Officer', 'HR Administrator')"
                )
            )
            officer_uids = {row[0] for row in officers}

        approvers: set[int] = set(officer_uids)
        if manager_uid:
            approvers.add(manager_uid)
        approvers.discard(requester_uid)  # never approve your own (escalates to officers)
        return approvers

    @classmethod
    async def _first_approver(cls, env: Environment, lid: int) -> int | None:
        rows = await super().read(env, [lid], ["first_approver_id"])
        return rows[0]["first_approver_id"] if rows else None


async def _leave_type(env: Environment, type_id: int) -> dict[str, Any]:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT request_unit, is_paid, allocation_required, allow_negative, "
                "approval_mode FROM hr_leave_type WHERE id = :i"
            ),
            {"i": type_id},
        )
        r = row.fetchone()
    if not r:
        raise DodooError("leave_type_not_found")
    return dict(r._mapping)


async def _employee_company(env: Environment, employee_id: int) -> int:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT company_id FROM hr_employee WHERE id = :i"), {"i": employee_id}
        )
        r = row.fetchone()
    if not r:
        raise DodooError("employee_not_found")
    return r[0]


def _as_date(value: Any) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _as_dt(value: Any) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())
    return datetime.datetime.fromisoformat(str(value))
