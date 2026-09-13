"""``stock.move.line`` — the actual quantity moved for a ``stock.move`` (FR-026)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Float, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockMoveLine(BaseModel):
    _name = "stock.move.line"

    move_id = Many2one("stock.move", required=True)
    qty_done = Float(required=True, default=0)
    location_src_id = Many2one("stock.location", required=True)
    location_dest_id = Many2one("stock.location", required=True)
    lot_id = Many2one("stock.lot")
    package_id = Many2one("stock.quant.package")
    result_package_id = Many2one("stock.quant.package")

    @classmethod
    async def _assert_tracking_requirements(
        cls, env: Environment, product_id: int, lot_id: int | None, qty_done: float
    ) -> None:
        """FR-045/046: a lot/serial-tracked product's move line requires a lot/serial value;
        a serial line must be exactly one unit and not currently on hand elsewhere."""
        from dodoo.addons.stock.models.product_product_ext import get_tracking
        from dodoo.addons.stock.models.stock_lot import StockLot

        tracking = await get_tracking(env, product_id)
        if tracking == "none":
            return
        if not lot_id:
            raise DodooError("lot_required")
        if tracking == "serial":
            if qty_done != 1:
                raise DodooError("serial_qty_must_be_one")
            on_hand = await StockLot.on_hand_elsewhere(env, lot_id, product_id)
            if on_hand > 0:
                raise DodooError("serial_already_on_hand")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        if vals.get("qty_done", 0) > 0:
            from dodoo.addons.stock.models.stock_move import StockMove

            move_rows = await StockMove.read(env, [vals["move_id"]], ["product_id"])
            if move_rows:
                await cls._assert_tracking_requirements(
                    env, move_rows[0]["product_id"], vals.get("lot_id"), vals.get("qty_done", 0)
                )
        return await super().create(env, vals)
