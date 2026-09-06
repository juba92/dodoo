"""``hr.job`` — a job position with target vs. current headcount (FR-003, FR-032)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.fields import Boolean, Char, Integer, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class HrJob(BaseModel):
    _name = "hr.job"

    name = Char(size=128, required=True)
    department_id = Many2one("hr.department")
    company_id = Many2one("res.company", required=True)
    expected_employees = Integer(default=0)
    is_published = Boolean(default=False)
    active = Boolean(default=True)

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        rows = await super().read(env, ids, fields)
        if fields is None or "no_of_employees" in fields:
            counts = await cls._headcounts(env, [r["id"] for r in rows])
            for r in rows:
                r["no_of_employees"] = counts.get(r["id"], 0)
        return rows

    @classmethod
    async def _headcounts(cls, env: Environment, ids: list[int]) -> dict[int, int]:
        if not ids:
            return {}
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT job_id, COUNT(*) FROM hr_employee "
                    "WHERE active = TRUE AND job_id = ANY(:ids) GROUP BY job_id"
                ),
                {"ids": ids},
            )
            return {r[0]: r[1] for r in rows}
