"""``hr.department`` — hierarchical organisational unit (FR-002)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Integer, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class HrDepartment(BaseModel):
    _name = "hr.department"

    name = Char(size=128, required=True)
    parent_id = Many2one("hr.department")
    manager_id = Many2one("hr.employee")
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)
    # Department-level appraisal cadence override (ADR-026); resolved after the
    # per-employee override and before the template default.
    appraisal_frequency_months = Integer()

    @classmethod
    async def _assert_no_cycle(
        cls, env: Environment, dept_id: int | None, parent_id: int | None
    ) -> None:
        """Reject a parent assignment that would make the hierarchy loop."""
        if not parent_id:
            return
        if parent_id == dept_id:
            raise DodooError("department_cycle")
        seen: set[int] = set()
        cur: int | None = parent_id
        async with env.dml_conn() as conn:
            while cur is not None:
                if cur == dept_id or cur in seen:
                    raise DodooError("department_cycle")
                seen.add(cur)
                row = await conn.execute(
                    text("SELECT parent_id FROM hr_department WHERE id = :i"), {"i": cur}
                )
                r = row.fetchone()
                cur = r[0] if r else None

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        await cls._assert_no_cycle(env, None, vals.get("parent_id"))
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if "parent_id" in vals:
            for dept_id in ids:
                await cls._assert_no_cycle(env, dept_id, vals["parent_id"])
        return await super().write(env, ids, vals)

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        want = fields is None or "complete_name" in fields
        fetch = fields
        if want and fields is not None and "id" not in fields:
            fetch = ["id", *fields]
        rows = await super().read(env, ids, fetch)
        if want and rows:
            names = await cls._complete_names(env, [r["id"] for r in rows])
            for r in rows:
                r["complete_name"] = names.get(r["id"], r.get("name"))
        return rows

    @classmethod
    async def _complete_names(
        cls, env: Environment, ids: list[int]
    ) -> dict[int, str]:
        if not ids:
            return {}
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text("SELECT id, name, parent_id FROM hr_department")
            )
            by_id = {r[0]: (r[1], r[2]) for r in rows}
        out: dict[int, str] = {}
        for dept_id in ids:
            parts: list[str] = []
            cur: int | None = dept_id
            guard = 0
            while cur is not None and cur in by_id and guard < 64:
                name, parent = by_id[cur]
                parts.append(name)
                cur = parent
                guard += 1
            out[dept_id] = " / ".join(reversed(parts))
        return out
