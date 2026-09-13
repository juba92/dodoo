"""``stock.lot`` — a batch (lot) or unique unit (serial) identifier (FR-044)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.stock.validators import and_domain
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Date, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockLot(BaseModel):
    _name = "stock.lot"

    name = Char(size=64, required=True)
    product_id = Many2one("product.product", required=True)
    company_id = Many2one("res.company")
    expiration_date = Date()

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        existing = await cls.search(
            env,
            and_domain(
                ["product_id", "=", vals["product_id"]], ["name", "=", vals["name"]]
            ),
        )
        if existing:
            raise DodooError("lot_name_not_unique")
        return await super().create(env, vals)

    @classmethod
    async def on_hand_elsewhere(cls, env: Environment, lot_id: int, product_id: int) -> float:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(quantity), 0) FROM stock_quant "
                    "WHERE lot_id = :lot AND product_id = :p"
                ),
                {"lot": lot_id, "p": product_id},
            )
            return float(row.scalar_one())

    @classmethod
    async def get_events(cls, env: Environment, lot_id: int) -> list[dict[str, Any]]:
        """Every transfer (and its move lines) that touched this lot, chronologically
        (FR-048)."""
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT ml.move_id, m.picking_id, m.create_date, ml.location_src_id, "
                    "ml.location_dest_id, ml.qty_done, ml.package_id "
                    "FROM stock_move_line ml JOIN stock_move m ON m.id = ml.move_id "
                    "WHERE ml.lot_id = :lot ORDER BY m.create_date"
                ),
                {"lot": lot_id},
            )
            return [dict(r._mapping) for r in rows]
