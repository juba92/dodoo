"""Skill taxonomy + per-employee proficiency (FR-017…FR-019).

``hr.skill.type`` groups ``hr.skill`` (competencies) and ``hr.skill.level`` (ordered rungs
with a progress %). ``hr.employee.skill`` links an employee → skill → level, with two guards:
the level must belong to the skill's type, and a skill cannot be added twice to one employee.
All catalog models are global (no ``company_id``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Integer, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class HrSkillType(BaseModel):
    _name = "hr.skill.type"

    name = Char(size=64, required=True)
    active = Boolean(default=True)


class HrSkill(BaseModel):
    _name = "hr.skill"

    name = Char(size=64, required=True)
    skill_type_id = Many2one("hr.skill.type", required=True)
    sequence = Integer(default=10)


class HrSkillLevel(BaseModel):
    _name = "hr.skill.level"

    name = Char(size=64, required=True)
    skill_type_id = Many2one("hr.skill.type", required=True)
    level_progress = Integer(default=0)
    sequence = Integer(default=10)

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        _check_progress(vals.get("level_progress"))
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if "level_progress" in vals:
            _check_progress(vals["level_progress"])
        return await super().write(env, ids, vals)


class HrEmployeeSkill(BaseModel):
    _name = "hr.employee.skill"

    employee_id = Many2one("hr.employee", required=True)
    skill_id = Many2one("hr.skill", required=True)
    skill_level_id = Many2one("hr.skill.level", required=True)
    # Denormalised for grouping the skills section by type on the employee form.
    skill_type_id = Many2one("hr.skill.type")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        await cls._validate(env, vals, exclude_id=None)
        vals = {**vals, "skill_type_id": await _type_of_skill(env, vals["skill_id"])}
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if {"skill_id", "skill_level_id", "employee_id"} & set(vals):
            for rec_id in ids:
                merged = await _row(env, rec_id)
                merged.update(vals)
                await cls._validate(env, merged, exclude_id=rec_id)
            if "skill_id" in vals:
                vals = {
                    **vals,
                    "skill_type_id": await _type_of_skill(env, vals["skill_id"]),
                }
        return await super().write(env, ids, vals)

    @classmethod
    async def _validate(
        cls, env: Environment, vals: dict[str, Any], exclude_id: int | None
    ) -> None:
        skill_id = vals.get("skill_id")
        level_id = vals.get("skill_level_id")
        employee_id = vals.get("employee_id")
        if skill_id and level_id:
            skill_type = await _type_of_skill(env, skill_id)
            level_type = await _type_of_level(env, level_id)
            if skill_type != level_type:
                raise DodooError("skill_level_mismatch")
        if skill_id and employee_id:
            async with env.dml_conn() as conn:
                params: dict[str, Any] = {"e": employee_id, "s": skill_id}
                sql = (
                    "SELECT 1 FROM hr_employee_skill "
                    "WHERE employee_id = :e AND skill_id = :s"
                )
                if exclude_id is not None:
                    sql += " AND id <> :x"
                    params["x"] = exclude_id
                row = await conn.execute(text(sql + " LIMIT 1"), params)
                if row.fetchone():
                    raise DodooError("skill_duplicate")


def _check_progress(value: Any) -> None:
    if value is None:
        return
    if not (0 <= int(value) <= 100):
        raise DodooError("skill_level_progress_range")


async def _type_of_skill(env: Environment, skill_id: int) -> int | None:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT skill_type_id FROM hr_skill WHERE id = :i"), {"i": skill_id}
        )
        r = row.fetchone()
        return r[0] if r else None


async def _type_of_level(env: Environment, level_id: int) -> int | None:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT skill_type_id FROM hr_skill_level WHERE id = :i"),
            {"i": level_id},
        )
        r = row.fetchone()
        return r[0] if r else None


async def _row(env: Environment, rec_id: int) -> dict[str, Any]:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT employee_id, skill_id, skill_level_id "
                "FROM hr_employee_skill WHERE id = :i"
            ),
            {"i": rec_id},
        )
        r = row.fetchone()
        return {
            "employee_id": r[0],
            "skill_id": r[1],
            "skill_level_id": r[2],
        } if r else {}
