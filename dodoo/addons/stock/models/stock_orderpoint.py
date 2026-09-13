"""``stock.warehouse.orderpoint`` — min/max replenishment (ADR-032, FR-063…066).

Triggered on demand only — via ``run_reordering`` — there is no background scheduler (FR-063a,
D6's sibling decision for the "no cron subsystem" constraint).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from dodoo.addons.stock.validators import and_domain
from dodoo.core.fields import Float, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockWarehouseOrderpoint(BaseModel):
    _name = "stock.warehouse.orderpoint"

    product_id = Many2one("product.product", required=True)
    location_id = Many2one("stock.location", required=True)
    product_min_qty = Float(required=True)
    product_max_qty = Float(required=True)
    qty_multiple = Float(default=1.0)

    @classmethod
    async def run_reordering(
        cls, env: Environment, orderpoint_ids: list[int] | None = None, uid: int | None = None
    ) -> dict[str, Any]:
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_picking import StockPicking
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType
        from dodoo.addons.stock.models.stock_quant import StockQuant
        from dodoo.addons.stock.models.stock_route import StockRoute, StockRule

        ids = orderpoint_ids if orderpoint_ids is not None else await cls.search(env, [])
        triggered: list[dict[str, Any]] = []
        skipped_covered: list[int] = []
        unresolved: list[int] = []

        for oid in ids:
            op = (
                await cls.read(
                    env,
                    [oid],
                    ["product_id", "location_id", "product_min_qty", "product_max_qty", "qty_multiple"],
                )
            )[0]
            # `forecasted` already nets out incoming (not-done/cancelled) moves (FR-011), so a
            # deficit computed from it is already short of any existing incoming transfer —
            # subtracting incoming a second time here would double-count it (FR-065).
            forecast_data = await StockQuant.get_forecast(env, op["product_id"], op["location_id"])
            forecast = forecast_data["forecasted"]
            if forecast >= op["product_min_qty"]:
                if forecast_data["incoming"] > 0:
                    skipped_covered.append(oid)
                continue

            deficit = op["product_max_qty"] - forecast
            multiple = op["qty_multiple"] or 1.0
            qty = math.ceil(deficit / multiple) * multiple

            loc = (await StockLocation.read(env, [op["location_id"]], ["warehouse_id"]))[0]
            warehouse_id = loc["warehouse_id"]
            if not warehouse_id:
                unresolved.append(oid)
                continue

            picking_ids: list[int] = []
            route_id = await StockRoute.get_applicable_route(env, op["product_id"], warehouse_id)
            if route_id:
                rule_ids = await StockRule.search(env, [["route_id", "=", route_id]])
                rules = (
                    await StockRule.read(
                        env,
                        rule_ids,
                        ["location_src_id", "location_dest_id", "picking_type_id"],
                    )
                    if rule_ids
                    else []
                )
                by_dest = {r["location_dest_id"]: r for r in rules}
                target = op["location_id"]
                chain = []
                seen: set[int] = set()
                while target in by_dest and target not in seen:
                    seen.add(target)
                    r = by_dest[target]
                    chain.append(r)
                    target = r["location_src_id"]
                chain.reverse()
                for r in chain:
                    pid = await StockPicking.create_with_moves(
                        env,
                        {"picking_type_id": r["picking_type_id"], "origin": f"orderpoint {oid}"},
                        [
                            {
                                "product_id": op["product_id"],
                                "product_uom_qty": qty,
                                "location_src_id": r["location_src_id"],
                                "location_dest_id": r["location_dest_id"],
                            }
                        ],
                    )
                    picking_ids.append(pid)

            if not picking_ids:
                # No-Purchase-app fallback (Clarifications, ADR-032): a direct Receipt from
                # the warehouse's Vendors location.
                recv_ids = await StockPickingType.search(
                    env,
                    and_domain(
                        ["warehouse_id", "=", warehouse_id],
                        ["code", "=", "incoming"],
                        ["name", "=", "Receipts"],
                    ),
                )
                if not recv_ids:
                    unresolved.append(oid)
                    continue
                pt = (
                    await StockPickingType.read(env, [recv_ids[0]], ["default_location_src_id"])
                )[0]
                pid = await StockPicking.create_with_moves(
                    env,
                    {"picking_type_id": recv_ids[0], "origin": f"orderpoint {oid}"},
                    [
                        {
                            "product_id": op["product_id"],
                            "product_uom_qty": qty,
                            "location_src_id": pt["default_location_src_id"],
                            "location_dest_id": op["location_id"],
                        }
                    ],
                )
                picking_ids.append(pid)

            triggered.append({"orderpoint_id": oid, "picking_ids": picking_ids})

        return {
            "triggered": triggered,
            "skipped_covered": skipped_covered,
            "unresolved": unresolved,
        }
