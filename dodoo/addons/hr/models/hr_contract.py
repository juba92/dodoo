"""``hr.contract`` — the contract-state engine (ADR-024, FR-011…FR-016)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.hr._audit import log_conflict, log_transition
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Date, Many2one, Monetary, Selection, Text
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STATE = [
    ("draft", "Draft"),
    ("running", "Running"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
]

# Legal manual transitions (ADR-024).
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"running", "cancelled"},
    "running": {"expired", "cancelled"},
    "expired": {"draft"},
    "cancelled": {"draft"},
}


class HrContract(BaseModel):
    _name = "hr.contract"

    name = Char(size=128, required=True)
    employee_id = Many2one("hr.employee", required=True)
    company_id = Many2one("res.company", required=True)
    contract_type_id = Many2one("hr.contract.type")
    currency_id = Many2one("res.currency")
    wage = Monetary()
    date_start = Date(required=True)
    date_end = Date()
    trial_date_end = Date()
    state = Selection(STATE, default="draft")
    notes = Text()

    # ------------------------------------------------------------------ guards
    @staticmethod
    def _check_dates(vals: dict[str, Any], current: dict[str, Any] | None = None) -> None:
        base = dict(current or {})
        base.update({k: v for k, v in vals.items() if v is not None})
        start = _as_date(base.get("date_start"))
        end = _as_date(base.get("date_end"))
        trial = _as_date(base.get("trial_date_end"))
        if start and end and end < start:
            raise DodooError("contract_dates")
        if trial:
            if start and trial < start:
                raise DodooError("contract_trial")
            if end and trial > end:
                raise DodooError("contract_trial")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        cls._check_dates(vals)
        if vals.get("state") == "running":
            await cls._assert_no_other_running(env, vals["employee_id"], None)
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if {"date_start", "date_end", "trial_date_end"} & set(vals):
            for cid in ids:
                cur = await super().read(
                    env, [cid], ["date_start", "date_end", "trial_date_end"]
                )
                cls._check_dates(vals, cur[0] if cur else None)
        return await super().write(env, ids, vals)

    @classmethod
    async def _assert_no_other_running(
        cls, env: Environment, employee_id: int, exclude_id: int | None
    ) -> None:
        async with env.dml_conn() as conn:
            params: dict[str, Any] = {"e": employee_id}
            sql = (
                "SELECT 1 FROM hr_contract "
                "WHERE employee_id = :e AND state = 'running'"
            )
            if exclude_id is not None:
                sql += " AND id <> :x"
                params["x"] = exclude_id
            row = await conn.execute(text(sql + " LIMIT 1"), params)
            if row.fetchone():
                raise DodooError("contract_running_exists")

    # ------------------------------------------------------------------ state
    @classmethod
    async def action_set_state(
        cls,
        env: Environment,
        ids: list[int],
        target: str,
        uid: int | None = None,
        expected_state: str | None = None,
    ) -> bool:
        if target not in dict(STATE):
            raise DodooError("contract_transition_invalid")
        for cid in ids:
            rows = await super().read(env, [cid], ["state", "employee_id", "company_id"])
            if not rows:
                raise DodooError("contract_not_found")
            current = rows[0]["state"]
            if expected_state is not None and expected_state != current:
                log_conflict(
                    _log,
                    model=cls._name,
                    record_id=cid,
                    event="contract_state_conflict",
                    expected=expected_state,
                    actual=current,
                    actor_uid=uid,
                )
                raise DodooError("contract_state_conflict")
            if target == current:
                continue
            if target not in _TRANSITIONS.get(current, set()):
                raise DodooError("contract_transition_invalid")
            if target == "running":
                await cls._assert_no_other_running(env, rows[0]["employee_id"], cid)
            await super().write(env, [cid], {"state": target})
            log_transition(
                _log,
                model=cls._name,
                record_id=cid,
                event="contract_state",
                frm=current,
                to=target,
                actor_uid=uid,
                company_id=rows[0]["company_id"],
            )
        return True

    @staticmethod
    def _effective_state(row: dict[str, Any]) -> str:
        """A running contract past its end date reads as expired (FR-016)."""
        if row.get("state") == "running":
            end = _as_date(row.get("date_end"))
            if end and end < datetime.date.today():
                return "expired"
        return row.get("state")

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        fetch = fields
        if fields is not None and "state" in fields and "date_end" not in fields:
            fetch = [*fields, "date_end"]
        rows = await super().read(env, ids, fetch)
        drop_end = fetch is not fields
        for r in rows:
            if "state" in r:
                r["state"] = cls._effective_state(r)
            if drop_end:
                r.pop("date_end", None)
        return rows

    @classmethod
    async def get_running_contract(
        cls, env: Environment, employee_id: int
    ) -> dict[str, Any]:
        """The running contract covering today, else the latest running one (ADR-024)."""
        today = datetime.date.today()
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, date_start, date_end, wage FROM hr_contract "
                    "WHERE employee_id = :e AND state = 'running' "
                    "ORDER BY date_start DESC"
                ),
                {"e": employee_id},
            )
            running = [dict(r._mapping) for r in rows]
        for r in running:
            start = _as_date(r["date_start"])
            end = _as_date(r["date_end"])
            if start and start <= today and (end is None or end >= today):
                return {"contract_id": r["id"], "wage": r["wage"]}
        if running:
            return {"contract_id": running[0]["id"], "wage": running[0]["wage"]}
        return {"contract_id": None}

    @classmethod
    async def run_contract_expiry(cls, env: Environment) -> dict[str, int]:
        """Idempotently flip running contracts past their end date to expired (ADR-024)."""
        async with env.dml_conn() as conn:
            result = await conn.execute(
                text(
                    "UPDATE hr_contract SET state = 'expired', write_date = now() "
                    "WHERE state = 'running' AND date_end IS NOT NULL "
                    "AND date_end < CURRENT_DATE RETURNING id"
                )
            )
            ids = [r[0] for r in result]
            await conn.commit()
        for cid in ids:
            log_transition(
                _log,
                model=cls._name,
                record_id=cid,
                event="contract_state",
                frm="running",
                to="expired",
                actor_uid=None,
            )
        return {"expired": len(ids)}


def _as_date(value: Any) -> datetime.date | None:
    if value is None or isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
