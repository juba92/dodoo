"""``stock.quant`` — on-hand quantity of a product at a location, keyed by lot/package
(FR-011, D2). The reservation basis for every transfer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.stock.validators import and_domain
from dodoo.core.fields import Float, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockQuant(BaseModel):
    _name = "stock.quant"

    product_id = Many2one("product.product", required=True)
    location_id = Many2one("stock.location", required=True)
    lot_id = Many2one("stock.lot")
    package_id = Many2one("stock.quant.package")
    quantity = Float(required=True, default=0)
    reserved_quantity = Float(required=True, default=0)
    counted_quantity = Float()

    # ------------------------------------------------------------------ upsert

    @classmethod
    async def adjust_quantity(
        cls,
        env: Environment,
        product_id: int,
        location_id: int,
        delta: float,
        lot_id: int | None = None,
        package_id: int | None = None,
    ) -> int:
        """Increment (or decrement, ``delta`` < 0) the on-hand quantity for a key, creating the
        quant row if needed. Locks the row ``FOR UPDATE`` when it already exists (D2)."""
        async with env.dml_conn() as conn:
            sql = (
                "SELECT id, quantity FROM stock_quant WHERE product_id = :p AND location_id = :l "
                "AND lot_id IS NOT DISTINCT FROM :lot AND package_id IS NOT DISTINCT FROM :pkg "
                "FOR UPDATE"
            )
            row = (
                await conn.execute(
                    text(sql),
                    {"p": product_id, "l": location_id, "lot": lot_id, "pkg": package_id},
                )
            ).fetchone()
            if row:
                new_qty = float(row[1]) + delta
                await conn.execute(
                    text(
                        "UPDATE stock_quant SET quantity = :q, write_date = now() WHERE id = :id"
                    ),
                    {"q": new_qty, "id": row[0]},
                )
                await conn.commit()
                return row[0]
            await conn.commit()
        return await cls.create(
            env,
            {
                "product_id": product_id,
                "location_id": location_id,
                "lot_id": lot_id,
                "package_id": package_id,
                "quantity": delta,
            },
        )

    # ------------------------------------------------------------------ reservation

    @classmethod
    async def available_quantity(
        cls, env: Environment, product_id: int, location_id: int
    ) -> float:
        """Sum of on-hand minus reserved across every lot/package at this product/location."""
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(quantity - reserved_quantity), 0) FROM stock_quant "
                    "WHERE product_id = :p AND location_id = :l"
                ),
                {"p": product_id, "l": location_id},
            )
            return float(row.scalar_one())

    @classmethod
    async def reserve(
        cls, env: Environment, product_id: int, location_id: int, qty: float
    ) -> float:
        """Reserve up to ``qty`` at this product/location, locking candidate rows ``FOR
        UPDATE`` (D2). Returns the quantity actually reserved (may be less than ``qty``)."""
        remaining = qty
        reserved_total = 0.0
        async with env.dml_conn() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, quantity, reserved_quantity FROM stock_quant "
                        "WHERE product_id = :p AND location_id = :l AND quantity > reserved_quantity "
                        "ORDER BY id FOR UPDATE"
                    ),
                    {"p": product_id, "l": location_id},
                )
            ).fetchall()
            for qid, on_hand, reserved in rows:
                if remaining <= 0:
                    break
                free = float(on_hand) - float(reserved)
                take = min(free, remaining)
                if take <= 0:
                    continue
                await conn.execute(
                    text(
                        "UPDATE stock_quant SET reserved_quantity = reserved_quantity + :t, "
                        "write_date = now() WHERE id = :id"
                    ),
                    {"t": take, "id": qid},
                )
                remaining -= take
                reserved_total += take
            await conn.commit()
        return reserved_total

    @classmethod
    async def release_reservation(
        cls, env: Environment, product_id: int, location_id: int, qty: float
    ) -> None:
        async with env.dml_conn() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, reserved_quantity FROM stock_quant "
                        "WHERE product_id = :p AND location_id = :l AND reserved_quantity > 0 "
                        "ORDER BY id FOR UPDATE"
                    ),
                    {"p": product_id, "l": location_id},
                )
            ).fetchall()
            remaining = qty
            for qid, reserved in rows:
                if remaining <= 0:
                    break
                release = min(float(reserved), remaining)
                await conn.execute(
                    text(
                        "UPDATE stock_quant SET reserved_quantity = reserved_quantity - :r, "
                        "write_date = now() WHERE id = :id"
                    ),
                    {"r": release, "id": qid},
                )
                remaining -= release
            await conn.commit()

    # ------------------------------------------------------------------ forecast

    @classmethod
    async def get_forecast(
        cls, env: Environment, product_id: int, location_id: int | None = None
    ) -> dict[str, float]:
        """on_hand / reserved / incoming / outgoing / forecasted (FR-011/034)."""
        async with env.dml_conn() as conn:
            loc_clause = " AND q.location_id = :loc" if location_id else ""
            params: dict[str, Any] = {"p": product_id}
            if location_id:
                params["loc"] = location_id
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(q.quantity),0), COALESCE(SUM(q.reserved_quantity),0) "
                    "FROM stock_quant q JOIN stock_location l ON l.id = q.location_id "
                    f"WHERE q.product_id = :p AND l.usage = 'internal'{loc_clause}"
                ),
                params,
            )
            on_hand, reserved = row.fetchone()

            loc_clause_dest = " AND m.location_dest_id = :loc" if location_id else ""
            loc_clause_src = " AND m.location_src_id = :loc" if location_id else ""
            incoming_row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(m.product_uom_qty),0) FROM stock_move m "
                    "JOIN stock_location dl ON dl.id = m.location_dest_id "
                    "JOIN stock_location sl ON sl.id = m.location_src_id "
                    "WHERE m.product_id = :p AND m.state NOT IN ('done','cancelled') "
                    f"AND dl.usage = 'internal' AND sl.usage != 'internal'{loc_clause_dest}"
                ),
                params,
            )
            incoming = float(incoming_row.scalar_one())

            outgoing_row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(m.product_uom_qty),0) FROM stock_move m "
                    "JOIN stock_location sl ON sl.id = m.location_src_id "
                    "JOIN stock_location dl ON dl.id = m.location_dest_id "
                    "WHERE m.product_id = :p AND m.state NOT IN ('done','cancelled') "
                    f"AND sl.usage = 'internal' AND dl.usage != 'internal'{loc_clause_src}"
                ),
                params,
            )
            outgoing = float(outgoing_row.scalar_one())

        on_hand = float(on_hand)
        reserved = float(reserved)
        return {
            "on_hand": on_hand,
            "reserved": reserved,
            "incoming": incoming,
            "outgoing": outgoing,
            "forecasted": on_hand + incoming - outgoing,
        }

    # ------------------------------------------------------------------ physical inventory

    @classmethod
    async def apply_count(
        cls, env: Environment, quant_ids: list[int], uid: int | None = None
    ) -> dict[str, Any]:
        """For every quant whose ``counted_quantity`` differs from ``quantity``, create an
        adjustment move to/from the location's warehouse inventory-loss location, drive it to
        done via the shared choke point, log the delta, and clear ``counted_quantity``
        (FR-038/039)."""
        from dodoo.addons.stock.models.stock_inventory_adjustment import (
            StockInventoryAdjustmentLog,
        )
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_move_line import StockMoveLine

        rows = await cls.read(
            env, quant_ids, ["product_id", "location_id", "lot_id", "quantity", "counted_quantity"]
        )
        applied = 0
        skipped = 0
        log_ids: list[int] = []
        for row in rows:
            if row["counted_quantity"] is None:
                skipped += 1
                continue
            before = row["quantity"]
            after = row["counted_quantity"]
            difference = after - before
            if abs(difference) < 1e-9:
                await super().write(env, [row["id"]], {"counted_quantity": None})
                skipped += 1
                continue

            loc = (await StockLocation.read(env, [row["location_id"]], ["warehouse_id"]))[0]
            loss_ids = await StockLocation.search(
                env,
                and_domain(
                    ["warehouse_id", "=", loc["warehouse_id"]]
                    if loc["warehouse_id"]
                    else ["id", "=", 0],
                    ["usage", "=", "inventory"],
                ),
            )
            if not loss_ids:
                loss_ids = [
                    await StockLocation.create(
                        env,
                        {
                            "name": "Inventory Adjustment",
                            "usage": "inventory",
                            "warehouse_id": loc["warehouse_id"],
                        },
                    )
                ]
            loss_id = loss_ids[0]

            if difference > 0:
                src, dst = loss_id, row["location_id"]
                qty = difference
            else:
                src, dst = row["location_id"], loss_id
                qty = -difference

            move_id = await StockMove.create(
                env,
                {
                    "product_id": row["product_id"],
                    "product_uom_qty": qty,
                    "location_src_id": src,
                    "location_dest_id": dst,
                    "origin": f"inventory adjustment (quant {row['id']})",
                },
            )
            await StockMoveLine.create(
                env,
                {
                    "move_id": move_id,
                    "qty_done": qty,
                    "location_src_id": src,
                    "location_dest_id": dst,
                    "lot_id": row["lot_id"],
                },
            )
            await cls.adjust_quantity(env, row["product_id"], src, -qty, lot_id=row["lot_id"])
            await cls.adjust_quantity(env, row["product_id"], dst, qty, lot_id=row["lot_id"])
            await StockMove.action_set_state(env, [move_id], "done", uid=uid)
            await super().write(env, [row["id"]], {"quantity": after, "counted_quantity": None})

            log_id = await StockInventoryAdjustmentLog.create(
                env,
                {
                    "product_id": row["product_id"],
                    "location_id": row["location_id"],
                    "lot_id": row["lot_id"],
                    "qty_before": before,
                    "qty_after": after,
                    "difference": difference,
                    "uid": uid,
                    "move_id": move_id,
                },
            )
            log_ids.append(log_id)
            applied += 1

        return {"applied": applied, "skipped": skipped, "log_ids": log_ids}
