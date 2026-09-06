"""``hr.appraisal.feedback`` — one feedback row for one side of one appraisal (FR-042).

The opposite side cannot read a row with ``is_visible = False`` — enforced in the model
layer (``read`` / ``search_read``), not only the UI. Writes are restricted to the owning side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError
from dodoo.core.fields import Boolean, Char, Many2one, Selection, Text
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

SIDE = [("employee", "Employee"), ("manager", "Manager")]


class HrAppraisalFeedback(BaseModel):
    _name = "hr.appraisal.feedback"

    appraisal_id = Many2one("hr.appraisal", required=True)
    side = Selection(SIDE, required=True)
    section_title = Char(size=128)
    content = Text()
    is_visible = Boolean(default=False)

    @classmethod
    async def _caller_side(
        cls, env: Environment, appraisal_id: int, uid: int | None
    ) -> str | None:
        if not uid:
            return None
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT e.user_id FROM hr_appraisal a "
                    "JOIN hr_employee e ON e.id = a.employee_id WHERE a.id = :i"
                ),
                {"i": appraisal_id},
            )
            r = row.fetchone()
        return "employee" if (r and r[0] == uid) else "manager"

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        rows = await super().read(env, ids, fields)
        uid = get_uid()
        if not rows:
            return rows
        # Group by appraisal to resolve the caller's side once per appraisal.
        sides: dict[int, str | None] = {}
        for r in rows:
            aid = r.get("appraisal_id")
            if aid not in sides:
                sides[aid] = await cls._caller_side(env, aid, uid)
        return [
            r
            for r in rows
            if r.get("is_visible")
            or r.get("side") == sides.get(r.get("appraisal_id"))
        ]

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        uid = get_uid()
        for fid in ids:
            cur = await super().read(env, [fid], ["appraisal_id", "side"])
            if not cur:
                continue
            side = await cls._caller_side(env, cur[0]["appraisal_id"], uid)
            if side != cur[0]["side"]:
                raise AccessError("feedback_wrong_side")
        return await super().write(env, ids, vals)
