"""``hr.employee`` — the anchor record for every other HR area (FR-001, FR-005…FR-008).

Fields are grouped (Personal / Work / Private / HR Settings) purely for the form UI; one table.
The Private-group + a few Personal fields are **sensitive**: ``read`` drops them for a caller
who is neither the linked user nor an HR Officer/Administrator (the ``res.users.password_hash``
precedent). This is a column-level filter on top of the ``ir.rule`` row filter (ADR-028).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.context import get_uid
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import (
    Boolean,
    Char,
    Date,
    Integer,
    Many2many,
    Many2one,
    Selection,
    Text,
)
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_SENSITIVE = frozenset(
    {
        "identification_id",
        "bank_account",
        "home_address",
        "birthday",
        "marital",
        "private_email",
        "private_phone",
        "emergency_contact",
        "emergency_phone",
        "dependant_count",
        "country_id",
    }
)

GENDER = [("male", "Male"), ("female", "Female"), ("other", "Other")]
MARITAL = [
    ("single", "Single"),
    ("married", "Married"),
    ("cohabitant", "Legal Cohabitant"),
    ("widower", "Widower"),
    ("divorced", "Divorced"),
]


class HrEmployee(BaseModel):
    _name = "hr.employee"

    name = Char(size=256, required=True)
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)

    # Work
    work_email = Char(size=256)
    work_phone = Char(size=64)
    department_id = Many2one("hr.department")
    job_id = Many2one("hr.job")
    job_title = Char(size=128)
    work_location = Char(size=128)
    manager_id = Many2one("hr.employee")
    coach_id = Many2one("hr.employee")

    # Personal
    photo = Text()
    gender = Selection(GENDER)
    birthday = Date()
    marital = Selection(MARITAL)
    private_email = Char(size=256)
    private_phone = Char(size=64)
    emergency_contact = Char(size=128)
    emergency_phone = Char(size=64)

    # Private (sensitive)
    country_id = Many2one("res.country")
    identification_id = Char(size=64)
    bank_account = Char(size=64)
    home_address = Text()
    dependant_count = Integer(default=0)

    # HR Settings
    user_id = Many2one("res.users")
    category_ids = Many2many(
        "hr.employee.category",
        relation_table="hr_employee_category_rel",
        column1="employee_id",
        column2="category_id",
    )
    next_appraisal_date = Date()
    appraisal_frequency_months = Integer()

    # ------------------------------------------------------------------ guards
    @classmethod
    async def _assert_manager_no_cycle(
        cls, env: Environment, emp_id: int | None, manager_id: int | None
    ) -> None:
        if not manager_id:
            return
        if manager_id == emp_id:
            raise DodooError("employee_cycle")
        seen: set[int] = set()
        cur: int | None = manager_id
        async with env.dml_conn() as conn:
            while cur is not None:
                if cur == emp_id or cur in seen:
                    raise DodooError("employee_cycle")
                seen.add(cur)
                row = await conn.execute(
                    text("SELECT manager_id FROM hr_employee WHERE id = :i"), {"i": cur}
                )
                r = row.fetchone()
                cur = r[0] if r else None

    @classmethod
    async def _assert_user_unique(
        cls,
        env: Environment,
        user_id: int | None,
        company_id: int | None,
        exclude_id: int | None,
    ) -> None:
        if not user_id or not company_id:
            return
        async with env.dml_conn() as conn:
            params: dict[str, Any] = {"u": user_id, "c": company_id}
            sql = (
                "SELECT 1 FROM hr_employee "
                "WHERE user_id = :u AND company_id = :c"
            )
            if exclude_id is not None:
                sql += " AND id <> :x"
                params["x"] = exclude_id
            row = await conn.execute(text(sql + " LIMIT 1"), params)
            if row.fetchone():
                raise DodooError("user_already_linked")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        await cls._assert_manager_no_cycle(env, None, vals.get("manager_id"))
        await cls._assert_user_unique(
            env, vals.get("user_id"), vals.get("company_id"), None
        )
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        for emp_id in ids:
            if "manager_id" in vals:
                await cls._assert_manager_no_cycle(env, emp_id, vals["manager_id"])
            if "user_id" in vals:
                cur = await super().read(env, [emp_id], ["company_id"])
                company_id = vals.get("company_id") or (
                    cur[0]["company_id"] if cur else None
                )
                await cls._assert_user_unique(
                    env, vals["user_id"], company_id, emp_id
                )
        return await super().write(env, ids, vals)

    # ------------------------------------------------------------------ read
    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        rows = await super().read(env, ids, fields)
        uid = get_uid()
        if await cls._may_see_sensitive(env, uid):
            return rows
        for r in rows:
            owner = r.get("user_id") == uid
            if owner:
                continue
            for key in _SENSITIVE:
                if key in r:
                    r[key] = None
        return rows

    @classmethod
    async def _may_see_sensitive(cls, env: Environment, uid: int | None) -> bool:
        if not uid:
            return False
        from dodoo.addons.hr.validators import group_names

        held = await group_names(env, uid)
        return bool(held & {"HR Officer", "HR Administrator"})

    # ------------------------------------------------------------------ helpers
    @classmethod
    async def resolve_current(cls, env: Environment) -> dict[str, Any]:
        """The employee record of the authenticated caller (FR-005)."""
        uid = get_uid()
        if not uid:
            return {"employee_id": None}
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT id FROM hr_employee WHERE user_id = :u AND active = TRUE "
                    "ORDER BY id LIMIT 1"
                ),
                {"u": uid},
            )
            r = row.fetchone()
        return {"employee_id": r[0] if r else None}

    @classmethod
    async def get_org_chart(
        cls, env: Environment, employee_id: int
    ) -> dict[str, Any]:
        """Manager chain (root→employee) and direct reports (FR-007)."""
        async with env.dml_conn() as conn:
            all_rows = await conn.execute(
                text(
                    "SELECT id, name, job_title, manager_id FROM hr_employee "
                    "WHERE active = TRUE"
                )
            )
            by_id = {
                r[0]: {"id": r[0], "name": r[1], "job_title": r[2], "manager_id": r[3]}
                for r in all_rows
            }
        if employee_id not in by_id:
            raise DodooError("employee_not_found")

        chain: list[dict[str, Any]] = []
        cur = by_id[employee_id]["manager_id"]
        guard = 0
        while cur is not None and cur in by_id and guard < 64:
            node = by_id[cur]
            chain.append(
                {"id": node["id"], "name": node["name"], "job_title": node["job_title"]}
            )
            cur = node["manager_id"]
            guard += 1
        chain.reverse()

        reports = [
            {"id": n["id"], "name": n["name"], "job_title": n["job_title"]}
            for n in by_id.values()
            if n["manager_id"] == employee_id
        ]
        return {"manager_chain": chain, "reports": reports}
