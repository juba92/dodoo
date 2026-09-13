"""``stock.quant.package`` / ``stock.package.type`` — handling units (FR-050…054)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.addons.stock.validators import and_domain
from dodoo.core.fields import Char, Float, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockPackageType(BaseModel):
    _name = "stock.package.type"

    name = Char(size=64, required=True)
    max_weight = Float()


class StockQuantPackage(BaseModel):
    _name = "stock.quant.package"

    name = Char(size=64)
    package_type_id = Many2one("stock.package.type")

    @classmethod
    async def move_package(
        cls, env: Environment, package_id: int, location_dest_id: int, uid: int | None = None
    ) -> int:
        """Relocate every quant in this package to ``location_dest_id`` as one Internal
        Transfer (FR-052)."""
        from dodoo.addons.stock.models.stock_picking import StockPicking
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType
        from dodoo.addons.stock.models.stock_quant import StockQuant

        quant_ids = await StockQuant.search(env, [["package_id", "=", package_id]])
        quants = (
            await StockQuant.read(env, quant_ids, ["product_id", "location_id", "quantity"])
            if quant_ids
            else []
        )
        if not quants:
            from dodoo.core.exceptions import DodooError

            raise DodooError("package_empty")

        src_location = quants[0]["location_id"]
        internal_ids = await StockPickingType.search(
            env, and_domain(["code", "=", "internal"], ["name", "=", "Internal Transfers"])
        )
        # Prefer the internal type whose default source matches, else the first internal type.
        picking_type_id = internal_ids[0] if internal_ids else None
        specs = [
            {
                "product_id": q["product_id"],
                "product_uom_qty": q["quantity"],
                "location_src_id": src_location,
                "location_dest_id": location_dest_id,
            }
            for q in quants
            if q["quantity"] > 0
        ]
        picking_id = await StockPicking.create_with_moves(
            env, {"picking_type_id": picking_type_id, "origin": f"package {package_id} move"}, specs
        )
        await StockPicking.action_confirm(env, picking_id, uid=uid)
        await StockPicking.action_validate(env, picking_id, uid=uid)
        # Move lines created by validate default to the package's own location key; retag them
        # onto the package so the whole package still travels together at the new location.
        from sqlalchemy import text

        async with env.dml_conn() as conn:
            await conn.execute(
                text(
                    "UPDATE stock_quant SET package_id = :pkg "
                    "WHERE location_id = :loc AND package_id IS NULL "
                    "AND product_id = ANY(:pids)"
                ),
                {
                    "pkg": package_id,
                    "loc": location_dest_id,
                    "pids": [q["product_id"] for q in quants],
                },
            )
            await conn.commit()
        return picking_id
