"""US2 — action_apply_steps topology generation (ADR-029)."""

from __future__ import annotations

from dodoo.addons.stock.validators import and_domain


async def test_one_step_warehouse_has_core_locations_and_types(env, company_id):
    from dodoo.addons.stock.models.stock_location import StockLocation
    from dodoo.addons.stock.models.stock_picking_type import StockPickingType
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse

    wid = await StockWarehouse.create(env, {"name": "One Step", "code": "OS1", "company_id": company_id})
    type_ids = await StockPickingType.search(env, [["warehouse_id", "=", wid]])
    types = {t["name"]: t for t in await StockPickingType.read(env, type_ids, ["name", "default_location_src_id", "default_location_dest_id"])}
    assert {"Receipts", "Delivery Orders", "Internal Transfers", "Returns"} <= set(types)

    wh = (await StockWarehouse.read(env, [wid], ["stock_location_id"]))[0]
    assert types["Receipts"]["default_location_dest_id"] == wh["stock_location_id"]
    assert types["Delivery Orders"]["default_location_src_id"] == wh["stock_location_id"]


async def test_two_step_delivery_creates_output_and_pick(env, company_id):
    from dodoo.addons.stock.models.stock_location import StockLocation
    from dodoo.addons.stock.models.stock_picking_type import StockPickingType
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse

    wid = await StockWarehouse.create(
        env, {"name": "Two Step", "code": "TS1", "company_id": company_id, "delivery_steps": "two_steps"}
    )
    output_ids = await StockLocation.search(
        env, and_domain(["warehouse_id", "=", wid], ["name", "=", "Output"])
    )
    assert len(output_ids) == 1

    pick_ids = await StockPickingType.search(
        env, and_domain(["warehouse_id", "=", wid], ["name", "=", "Pick"])
    )
    assert len(pick_ids) == 1


async def test_reapplying_steps_is_idempotent(env, company_id):
    from dodoo.addons.stock.models.stock_picking_type import StockPickingType
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse

    wid = await StockWarehouse.create(env, {"name": "Idempotent", "code": "IDP", "company_id": company_id})
    await StockWarehouse.action_apply_steps(env, wid)
    await StockWarehouse.action_apply_steps(env, wid)
    type_ids = await StockPickingType.search(env, [["warehouse_id", "=", wid]])
    names = [t["name"] for t in await StockPickingType.read(env, type_ids, ["name"])]
    assert sorted(names) == sorted(set(names)), "no duplicate picking types on re-apply"
