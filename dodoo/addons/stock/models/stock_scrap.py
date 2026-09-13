"""``stock.scrap`` — write off damaged/lost stock (FR-067…070)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Float, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

STATE_CHOICES = [("draft", "Draft"), ("done", "Done")]


class StockScrap(BaseModel):
    _name = "stock.scrap"

    product_id = Many2one("product.product", required=True)
    lot_id = Many2one("stock.lot")
    quantity = Float(required=True)
    location_src_id = Many2one("stock.location", required=True)
    location_dest_id = Many2one("stock.location", required=True)
    reason = Char(size=256)
    state = Selection(STATE_CHOICES, default="draft")
    move_id = Many2one("stock.move")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        if vals.get("quantity", 0) <= 0:
            raise DodooError("scrap_qty_must_be_positive")
        return await super().create(env, vals)

    @classmethod
    async def write(cls, env: Environment, ids: list[int], vals: dict[str, Any]) -> bool:
        for sid in ids:
            rows = await super().read(env, [sid], ["state"])
            if rows and rows[0]["state"] == "done":
                raise DodooError("scrap_locked_done")
        return await super().write(env, ids, vals)

    @classmethod
    async def unlink(cls, env: Environment, ids: list[int]) -> bool:
        for sid in ids:
            rows = await super().read(env, [sid], ["state"])
            if rows and rows[0]["state"] == "done":
                raise DodooError("scrap_locked_done")
        return await super().unlink(env, ids)

    @classmethod
    async def action_confirm(cls, env: Environment, scrap_id: int, uid: int | None = None) -> dict[str, Any]:
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_move_line import StockMoveLine
        from dodoo.addons.stock.models.stock_quant import StockQuant

        rec = (
            await super().read(
                env,
                [scrap_id],
                ["product_id", "lot_id", "quantity", "location_src_id", "location_dest_id", "state"],
            )
        )[0]
        if rec["state"] == "done":
            raise DodooError("scrap_locked_done")

        available = await StockQuant.available_quantity(
            env, rec["product_id"], rec["location_src_id"]
        )
        if rec["quantity"] > available + 1e-9:
            raise DodooError("scrap_qty_exceeds_on_hand")

        # Scrap moves stand alone (no picking) — write the quant deltas directly and drive a
        # bare move through the same action_set_state choke point stock_account hooks.
        move_id = await StockMove.create(
            env,
            {
                "product_id": rec["product_id"],
                "product_uom_qty": rec["quantity"],
                "location_src_id": rec["location_src_id"],
                "location_dest_id": rec["location_dest_id"],
                "origin": f"scrap {scrap_id}",
            },
        )

        await StockMoveLine.create(
            env,
            {
                "move_id": move_id,
                "qty_done": rec["quantity"],
                "location_src_id": rec["location_src_id"],
                "location_dest_id": rec["location_dest_id"],
                "lot_id": rec["lot_id"],
            },
        )
        await StockQuant.adjust_quantity(
            env, rec["product_id"], rec["location_src_id"], -rec["quantity"], lot_id=rec["lot_id"]
        )
        await StockQuant.adjust_quantity(
            env, rec["product_id"], rec["location_dest_id"], rec["quantity"], lot_id=rec["lot_id"]
        )
        await StockMove.action_set_state(env, [move_id], "done", uid=uid)
        await super().write(env, [scrap_id], {"state": "done", "move_id": move_id})
        return {"state": "done", "move_id": move_id}
