"""``stock.picking`` — a transfer document grouping one or more stock moves (ADR-030).

``state`` is **derived** from its moves' states, never written directly (ADR-030) — see
:meth:`get_state`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.addons.stock.validators import and_domain
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Datetime, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockPicking(BaseModel):
    _name = "stock.picking"

    name = Char(size=64)
    picking_type_id = Many2one("stock.picking.type", required=True)
    partner_id = Many2one("res.partner")
    origin = Char(size=256)
    backorder_id = Many2one("stock.picking")
    scheduled_date = Datetime()
    date_done = Datetime()

    # ------------------------------------------------------------------ derived state

    @classmethod
    async def get_state(cls, env: Environment, picking_id: int) -> str:
        from dodoo.addons.stock.models.stock_move import StockMove

        move_ids = await StockMove.search(env, [["picking_id", "=", picking_id]])
        if not move_ids:
            return "draft"
        moves = await StockMove.read(env, move_ids, ["state"])
        non_cancelled = [m["state"] for m in moves if m["state"] != "cancelled"]
        if not non_cancelled:
            return "cancelled"
        if all(s == "done" for s in non_cancelled):
            return "done"
        if all(s == "draft" for s in non_cancelled):
            return "draft"
        if all(s == "ready" for s in non_cancelled):
            return "ready"
        if any(s in ("confirmed", "ready") for s in non_cancelled):
            return "confirmed"
        return "waiting"

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        want_state = fields is None or "state" in fields
        fetch = [f for f in (fields or []) if f != "state"] or None
        rows = await super().read(env, ids, fetch)
        if want_state:
            for row in rows:
                row["state"] = await cls.get_state(env, row["id"])
        return rows

    # ------------------------------------------------------------------ creation

    @classmethod
    async def create_with_moves(
        cls, env: Environment, vals: dict[str, Any], move_specs: list[dict[str, Any]]
    ) -> int:
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType

        picking_id = await super().create(env, vals)
        pt = (
            await StockPickingType.read(
                env,
                [vals["picking_type_id"]],
                ["default_location_src_id", "default_location_dest_id"],
            )
        )[0]
        for spec in move_specs:
            if spec.get("product_uom_qty", 0) <= 0:
                raise DodooError("move_qty_must_be_positive")
            await StockMove.create(
                env,
                {
                    "picking_id": picking_id,
                    "product_id": spec["product_id"],
                    "product_uom_qty": spec["product_uom_qty"],
                    "product_uom_id": spec.get("product_uom_id"),
                    "location_src_id": spec.get("location_src_id")
                    or pt["default_location_src_id"],
                    "location_dest_id": spec.get("location_dest_id")
                    or pt["default_location_dest_id"],
                },
            )
        return picking_id

    # ------------------------------------------------------------------ workflow

    @classmethod
    async def action_confirm(cls, env: Environment, picking_id: int, uid: int | None = None) -> str:
        from dodoo.addons.stock.models.stock_move import StockMove

        move_ids = await StockMove.search(env, [["picking_id", "=", picking_id]])
        for move_id in move_ids:
            await StockMove.action_reserve(env, move_id, uid=uid)
        return await cls.get_state(env, picking_id)

    @classmethod
    async def action_validate(
        cls,
        env: Environment,
        picking_id: int,
        uid: int | None = None,
        expected_state: str | None = None,
        create_backorder: bool | None = None,
    ) -> dict[str, Any]:
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_move_line import StockMoveLine
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType
        from dodoo.addons.stock.models.stock_quant import StockQuant

        current = await cls.get_state(env, picking_id)
        if expected_state is not None and expected_state != current:
            raise DodooError("transfer_state_conflict")
        if current in ("done", "cancelled"):
            raise DodooError("transfer_state_conflict")

        picking = (await super().read(env, [picking_id], ["picking_type_id"]))[0]
        pt = (
            await StockPickingType.read(env, [picking["picking_type_id"]], ["backorder_policy"])
        )[0]

        move_ids = await StockMove.search(env, [["picking_id", "=", picking_id]])
        moves = await StockMove.read(
            env,
            move_ids,
            ["product_id", "product_uom_qty", "location_src_id", "location_dest_id", "state"],
        )

        backorder_lines: list[dict[str, Any]] = []
        for move in moves:
            if move["state"] in ("done", "cancelled"):
                continue
            # Reservation is tracked as a per-(product, location) pool, not per-move (a
            # deliberate simplification — see plan.md's scope notes); validating a move
            # consumes up to its demanded quantity from whatever is physically on hand
            # (the reservation held by `action_confirm` is what makes that safe to assume
            # for the reserved portion) — never more than total on-hand (FR-029). A
            # non-internal source (Vendors, …) is an unlimited supply (FR-016).
            src_usage = (await StockLocation.read(env, [move["location_src_id"]], ["usage"]))[0][
                "usage"
            ]
            demanded = move["product_uom_qty"]
            if src_usage != "internal":
                do_qty = demanded
            else:
                on_hand = await cls._total_on_hand(
                    env, move["product_id"], move["location_src_id"]
                )
                do_qty = max(0.0, min(demanded, on_hand))

            if do_qty > 0:
                from dodoo.addons.stock.models.stock_putaway_rule import StockPutawayRule

                putaway_dest = await StockPutawayRule.resolve_destination(
                    env, move["product_id"], move["location_dest_id"]
                )
                await StockMoveLine.create(
                    env,
                    {
                        "move_id": move["id"],
                        "qty_done": do_qty,
                        "location_src_id": move["location_src_id"],
                        "location_dest_id": putaway_dest,
                    },
                )
                await StockQuant.adjust_quantity(
                    env, move["product_id"], move["location_src_id"], -do_qty
                )
                await StockQuant.release_reservation(
                    env, move["product_id"], move["location_src_id"], do_qty
                )
                await StockQuant.adjust_quantity(
                    env, move["product_id"], putaway_dest, do_qty
                )

            remainder = demanded - do_qty
            if remainder > 1e-9:
                # Best-effort: free whatever reservation this shortfall would otherwise hold.
                await StockQuant.release_reservation(
                    env, move["product_id"], move["location_src_id"], remainder
                )
                if pt["backorder_policy"] == "always" or (
                    pt["backorder_policy"] == "ask" and create_backorder
                ):
                    backorder_lines.append(
                        {
                            "product_id": move["product_id"],
                            "product_uom_qty": remainder,
                            "location_src_id": move["location_src_id"],
                            "location_dest_id": move["location_dest_id"],
                        }
                    )

            if do_qty > 0:
                await StockMove.action_set_state(env, [move["id"]], "done", uid=uid)
            else:
                await StockMove.action_set_state(env, [move["id"]], "cancelled", uid=uid)

        backorder_id = None
        if backorder_lines:
            backorder_id = await cls.create_with_moves(
                env,
                {
                    "picking_type_id": picking["picking_type_id"],
                    "backorder_id": picking_id,
                    "origin": f"backorder of {picking_id}",
                },
                backorder_lines,
            )

        await super().write(env, [picking_id], {})  # touch write_date
        return {"state": await cls.get_state(env, picking_id), "backorder_id": backorder_id}

    @staticmethod
    async def _total_on_hand(env: Environment, product_id: int, location_id: int) -> float:
        from sqlalchemy import text

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(quantity), 0) FROM stock_quant "
                    "WHERE product_id = :p AND location_id = :l"
                ),
                {"p": product_id, "l": location_id},
            )
            return float(row.scalar_one())

    @staticmethod
    async def _move_reserved_qty(env: Environment, move: dict[str, Any]) -> float:
        from sqlalchemy import text

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(reserved_quantity), 0) FROM stock_quant "
                    "WHERE product_id = :p AND location_id = :l"
                ),
                {"p": move["product_id"], "l": move["location_src_id"]},
            )
            return float(row.scalar_one())

    @classmethod
    async def action_cancel(
        cls, env: Environment, picking_id: int, uid: int | None = None, expected_state: str | None = None
    ) -> str:
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_quant import StockQuant

        current = await cls.get_state(env, picking_id)
        if expected_state is not None and expected_state != current:
            raise DodooError("transfer_state_conflict")
        if current == "done":
            raise DodooError("transfer_done_not_cancellable")

        move_ids = await StockMove.search(env, [["picking_id", "=", picking_id]])
        moves = await StockMove.read(
            env, move_ids, ["product_id", "location_src_id", "product_uom_qty", "state"]
        )
        for move in moves:
            if move["state"] in ("done", "cancelled"):
                continue
            reserved = await cls._move_reserved_qty(env, move)
            if reserved > 0:
                await StockQuant.release_reservation(
                    env, move["product_id"], move["location_src_id"], min(reserved, move["product_uom_qty"])
                )
            await StockMove.action_set_state(env, [move["id"]], "cancelled", uid=uid)
        return "cancelled"

    @classmethod
    async def action_return(cls, env: Environment, picking_id: int, uid: int | None = None) -> int:
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_move_line import StockMoveLine
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType

        current = await cls.get_state(env, picking_id)
        if current != "done":
            raise DodooError("return_requires_done_transfer")

        picking = (await super().read(env, [picking_id], ["picking_type_id"]))[0]
        pt = (await StockPickingType.read(env, [picking["picking_type_id"]], ["warehouse_id"]))[0]
        returns_ids = await StockPickingType.search(
            env, and_domain(["warehouse_id", "=", pt["warehouse_id"]], ["name", "=", "Returns"])
        )
        if not returns_ids:
            raise DodooError("returns_type_not_found")

        move_ids = await StockMove.search(env, [["picking_id", "=", picking_id]])
        moves = await StockMove.read(
            env, move_ids, ["product_id", "location_src_id", "location_dest_id"]
        )
        move_lines_by_move: dict[int, float] = {}
        for mid in move_ids:
            line_ids = await StockMoveLine.search(env, [["move_id", "=", mid]])
            lines = await StockMoveLine.read(env, line_ids, ["qty_done"]) if line_ids else []
            move_lines_by_move[mid] = sum(l["qty_done"] for l in lines)

        specs = []
        for move in moves:
            qty = move_lines_by_move.get(move["id"], 0)
            if qty <= 0:
                continue
            specs.append(
                {
                    "product_id": move["product_id"],
                    "product_uom_qty": qty,
                    "location_src_id": move["location_dest_id"],
                    "location_dest_id": move["location_src_id"],
                }
            )
        return await cls.create_with_moves(
            env,
            {
                "picking_type_id": returns_ids[0],
                "origin": f"return of {picking_id}",
            },
            specs,
        )
