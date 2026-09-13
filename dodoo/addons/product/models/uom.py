"""``uom.category`` / ``uom.uom`` — units of measure and conversion (FR-002/003)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Float, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

UOM_TYPE_CHOICES = [
    ("reference", "Reference Unit"),
    ("bigger", "Bigger than Reference"),
    ("smaller", "Smaller than Reference"),
]


class UomCategory(BaseModel):
    _name = "uom.category"

    name = Char(size=64, required=True)


class UomUom(BaseModel):
    _name = "uom.uom"

    name = Char(size=64, required=True)
    category_id = Many2one("uom.category", required=True)
    uom_type = Selection(UOM_TYPE_CHOICES, required=True)
    ratio = Float(required=True, default=1.0)
    rounding = Float(default=0.01)

    @classmethod
    async def _assert_single_reference(
        cls, env: Environment, category_id: int, exclude_id: int | None
    ) -> None:
        async with env.dml_conn() as conn:
            from sqlalchemy import text

            sql = (
                "SELECT 1 FROM uom_uom WHERE category_id = :c AND uom_type = 'reference'"
            )
            params: dict[str, Any] = {"c": category_id}
            if exclude_id is not None:
                sql += " AND id <> :x"
                params["x"] = exclude_id
            row = await conn.execute(text(sql + " LIMIT 1"), params)
            if row.fetchone():
                raise DodooError("uom_reference_exists")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        if vals.get("uom_type") == "reference":
            await cls._assert_single_reference(env, vals["category_id"], None)
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if vals.get("uom_type") == "reference":
            for uid in ids:
                rows = await super().read(env, [uid], ["category_id"])
                if rows:
                    await cls._assert_single_reference(env, rows[0]["category_id"], uid)
        return await super().write(env, ids, vals)

    @classmethod
    async def convert(
        cls, env: Environment, qty: float, from_uom_id: int, to_uom_id: int
    ) -> float:
        """Convert ``qty`` expressed in ``from_uom_id`` to ``to_uom_id``.

        Both units must belong to the same ``uom.category`` (FR-003); ``ratio`` is each unit's
        factor relative to its category's reference unit.
        """
        if from_uom_id == to_uom_id:
            return qty
        rows = await super().read(env, [from_uom_id, to_uom_id], ["category_id", "ratio"])
        by_id = {r["id"]: r for r in rows}
        frm = by_id.get(from_uom_id)
        to = by_id.get(to_uom_id)
        if not frm or not to:
            raise DodooError("uom_not_found")
        if frm["category_id"] != to["category_id"]:
            raise DodooError("uom_category_mismatch")
        # Both ratios are relative to the same reference unit (ratio 1.0).
        return qty * float(frm["ratio"]) / float(to["ratio"])
