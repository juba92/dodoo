"""``stock.warehouse`` — a company's physical stock location + step-driven topology (ADR-029,
FR-013/014)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.stock.validators import and_domain
from dodoo.core.fields import Char, Many2one, Selection, Text
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STEP_CHOICES = [
    ("one_step", "One Step"),
    ("two_steps", "Two Steps"),
    ("three_steps", "Three Steps"),
]


class StockWarehouse(BaseModel):
    _name = "stock.warehouse"

    name = Char(size=128, required=True)
    code = Char(size=16, required=True)
    company_id = Many2one("res.company", required=True)
    address = Text()
    reception_steps = Selection(STEP_CHOICES, default="one_step")
    delivery_steps = Selection(STEP_CHOICES, default="one_step")
    view_location_id = Many2one("stock.location")
    stock_location_id = Many2one("stock.location")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        warehouse_id = await super().create(env, vals)
        await cls.action_apply_steps(env, warehouse_id)
        return warehouse_id

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        result = await super().write(env, ids, vals)
        if "reception_steps" in vals or "delivery_steps" in vals:
            for wid in ids:
                await cls.action_apply_steps(env, wid)
        return result

    # ------------------------------------------------------------------ helpers

    @classmethod
    async def _ensure_shared_location(
        cls, env: Environment, company_id: int, name: str, usage: str
    ) -> int:
        """A per-company Vendors/Customers location, reused across every warehouse."""
        from dodoo.addons.stock.models.stock_location import StockLocation

        ids = await StockLocation.search(
            env,
            and_domain(
                ["name", "=", name], ["usage", "=", usage], ["company_id", "=", company_id]
            ),
        )
        if ids:
            return ids[0]
        return await StockLocation.create(
            env, {"name": name, "usage": usage, "company_id": company_id}
        )

    @classmethod
    async def _ensure_child_location(
        cls,
        env: Environment,
        parent_id: int,
        warehouse_id: int,
        company_id: int,
        name: str,
        created: list[int],
    ) -> int:
        from dodoo.addons.stock.models.stock_location import StockLocation

        ids = await StockLocation.search(
            env,
            and_domain(
                ["warehouse_id", "=", warehouse_id],
                ["name", "=", name],
                ["active", "=", True],
            ),
        )
        if ids:
            return ids[0]
        lid = await StockLocation.create(
            env,
            {
                "name": name,
                "parent_id": parent_id,
                "usage": "internal",
                "warehouse_id": warehouse_id,
                "company_id": company_id,
            },
        )
        created.append(lid)
        return lid

    @classmethod
    async def _ensure_picking_type(
        cls,
        env: Environment,
        warehouse_id: int,
        name: str,
        code: str,
        src_id: int | None,
        dest_id: int | None,
        created: list[int],
    ) -> int:
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType

        ids = await StockPickingType.search(
            env, and_domain(["warehouse_id", "=", warehouse_id], ["name", "=", name])
        )
        if ids:
            await StockPickingType.write(
                env,
                ids,
                {"default_location_src_id": src_id, "default_location_dest_id": dest_id},
            )
            return ids[0]
        pid = await StockPickingType.create(
            env,
            {
                "name": name,
                "code": code,
                "warehouse_id": warehouse_id,
                "default_location_src_id": src_id,
                "default_location_dest_id": dest_id,
            },
        )
        created.append(pid)
        return pid

    @classmethod
    async def _archive_unused_locations(
        cls, env: Environment, warehouse_id: int, keep_names: set[str], candidate_names: list[str]
    ) -> list[int]:
        from dodoo.addons.stock.models.stock_location import StockLocation

        archived: list[int] = []
        for name in candidate_names:
            if name in keep_names:
                continue
            ids = await StockLocation.search(
                env,
                and_domain(
                    ["warehouse_id", "=", warehouse_id],
                    ["name", "=", name],
                    ["active", "=", True],
                ),
            )
            for lid in ids:
                has_history = False
                async with env.dml_conn() as conn:
                    try:
                        row = await conn.execute(
                            text(
                                "SELECT 1 FROM stock_quant WHERE location_id = :l "
                                "AND quantity <> 0 LIMIT 1"
                            ),
                            {"l": lid},
                        )
                        has_history = row.fetchone() is not None
                    except Exception:  # noqa: BLE001 — stock_quant may not exist yet
                        has_history = False
                if has_history:
                    continue
                await StockLocation.write(env, [lid], {"active": False})
                archived.append(lid)
        return archived

    @classmethod
    async def action_apply_steps(cls, env: Environment, warehouse_id: int) -> dict[str, list[int]]:
        """Idempotently ensure the location/operation-type topology for the current step
        configuration exists (ADR-029); archives (never deletes) locations made redundant by a
        step decrease, unless they already carry on-hand history (D4)."""
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType

        rows = await super().read(
            env,
            [warehouse_id],
            [
                "name",
                "code",
                "company_id",
                "reception_steps",
                "delivery_steps",
                "view_location_id",
                "stock_location_id",
            ],
        )
        wh = rows[0]
        company_id = wh["company_id"]

        view_id = wh["view_location_id"]
        if not view_id:
            view_id = await StockLocation.create(
                env,
                {"name": wh["code"], "usage": "view", "warehouse_id": warehouse_id, "company_id": company_id},
            )
            await super().write(env, [warehouse_id], {"view_location_id": view_id})

        stock_id = wh["stock_location_id"]
        if not stock_id:
            stock_id = await StockLocation.create(
                env,
                {
                    "name": "Stock",
                    "parent_id": view_id,
                    "usage": "internal",
                    "warehouse_id": warehouse_id,
                    "company_id": company_id,
                },
            )
            await super().write(env, [warehouse_id], {"stock_location_id": stock_id})

        vendor_loc = await cls._ensure_shared_location(env, company_id, "Vendors", "vendor")
        customer_loc = await cls._ensure_shared_location(env, company_id, "Customers", "customer")

        created_locations: list[int] = []
        created_types: list[int] = []

        recv_steps = wh["reception_steps"]
        input_id = None
        quality_id = None
        if recv_steps != "one_step":
            input_id = await cls._ensure_child_location(
                env, view_id, warehouse_id, company_id, "Input", created_locations
            )
        if recv_steps == "three_steps":
            quality_id = await cls._ensure_child_location(
                env, view_id, warehouse_id, company_id, "Quality Control", created_locations
            )

        recv_dest = stock_id if recv_steps == "one_step" else input_id
        await cls._ensure_picking_type(
            env, warehouse_id, "Receipts", "incoming", vendor_loc, recv_dest, created_types
        )
        if recv_steps == "two_steps":
            await cls._ensure_picking_type(
                env, warehouse_id, "Input to Stock", "internal", input_id, stock_id, created_types
            )
        elif recv_steps == "three_steps":
            await cls._ensure_picking_type(
                env, warehouse_id, "Input to Quality", "internal", input_id, quality_id, created_types
            )
            await cls._ensure_picking_type(
                env, warehouse_id, "Quality to Stock", "internal", quality_id, stock_id, created_types
            )

        keep = set()
        if recv_steps != "one_step":
            keep.add("Input")
        if recv_steps == "three_steps":
            keep.add("Quality Control")
        archived = await cls._archive_unused_locations(
            env, warehouse_id, keep, ["Input", "Quality Control"]
        )
        for name in ["Input to Stock", "Input to Quality", "Quality to Stock"]:
            if (name == "Input to Stock" and recv_steps == "two_steps") or (
                name in ("Input to Quality", "Quality to Stock") and recv_steps == "three_steps"
            ):
                continue
            stale_ids = await StockPickingType.search(
                env, and_domain(["warehouse_id", "=", warehouse_id], ["name", "=", name])
            )
            if stale_ids:
                await StockPickingType.write(
                    env, stale_ids, {"default_location_src_id": None, "default_location_dest_id": None}
                )

        del_steps = wh["delivery_steps"]
        output_id = None
        packing_id = None
        if del_steps != "one_step":
            output_id = await cls._ensure_child_location(
                env, view_id, warehouse_id, company_id, "Output", created_locations
            )
        if del_steps == "three_steps":
            packing_id = await cls._ensure_child_location(
                env, view_id, warehouse_id, company_id, "Packing Zone", created_locations
            )

        del_src = stock_id if del_steps == "one_step" else (packing_id if del_steps == "three_steps" else output_id)
        await cls._ensure_picking_type(
            env, warehouse_id, "Delivery Orders", "outgoing", del_src, customer_loc, created_types
        )
        if del_steps == "two_steps":
            await cls._ensure_picking_type(
                env, warehouse_id, "Pick", "internal", stock_id, output_id, created_types
            )
        elif del_steps == "three_steps":
            await cls._ensure_picking_type(
                env, warehouse_id, "Pick", "internal", stock_id, output_id, created_types
            )
            await cls._ensure_picking_type(
                env, warehouse_id, "Pack", "internal", output_id, packing_id, created_types
            )

        keep_out = set()
        if del_steps != "one_step":
            keep_out.add("Output")
        if del_steps == "three_steps":
            keep_out.add("Packing Zone")
        archived += await cls._archive_unused_locations(
            env, warehouse_id, keep_out, ["Output", "Packing Zone"]
        )

        await cls._ensure_picking_type(
            env, warehouse_id, "Internal Transfers", "internal", stock_id, stock_id, created_types
        )
        await cls._ensure_picking_type(
            env, warehouse_id, "Returns", "incoming", customer_loc, stock_id, created_types
        )

        return {
            "created_locations": created_locations,
            "created_picking_types": created_types,
            "archived_locations": archived,
        }
