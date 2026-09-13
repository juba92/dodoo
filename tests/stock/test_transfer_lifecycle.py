"""US3 — receipt -> deliver -> partial+backorder -> return, end to end (Independent Test)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def _fixture(env, company_id):
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom
    from dodoo.addons.stock.models.stock_picking_type import StockPickingType
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse
    from dodoo.addons.stock.validators import and_domain

    cat = await ProductCategory.create(env, {"name": "Lifecycle Cat"})
    uom_cat = await UomCategory.create(env, {"name": "Lifecycle Unit"})
    unit = await UomUom.create(
        env, {"name": "Unit LC", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0}
    )
    template = await ProductTemplate.create(
        env,
        {
            "name": "Lifecycle Product",
            "category_id": cat,
            "product_type": "goods",
            "is_storable": True,
            "uom_id": unit,
            "company_id": company_id,
        },
    )
    from dodoo.addons.product.models.product_product import ProductProduct

    product_id = (await ProductProduct.search(env, [["template_id", "=", template]]))[0]

    warehouse_id = await StockWarehouse.create(
        env, {"name": "Lifecycle WH", "code": "LCWH", "company_id": company_id}
    )
    receipts_id = (
        await StockPickingType.search(
            env, and_domain(["warehouse_id", "=", warehouse_id], ["name", "=", "Receipts"])
        )
    )[0]
    delivery_id = (
        await StockPickingType.search(
            env,
            and_domain(["warehouse_id", "=", warehouse_id], ["name", "=", "Delivery Orders"]),
        )
    )[0]
    return {
        "product_id": product_id,
        "unit_id": unit,
        "warehouse_id": warehouse_id,
        "receipts_id": receipts_id,
        "delivery_id": delivery_id,
    }


async def test_receipt_increases_on_hand(env, _fixture):
    from dodoo.addons.stock.models.stock_picking import StockPicking
    from dodoo.addons.stock.models.stock_quant import StockQuant

    picking_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [
            {
                "product_id": _fixture["product_id"],
                "product_uom_qty": 10,
                "product_uom_id": _fixture["unit_id"],
            }
        ],
    )
    await StockPicking.action_confirm(env, picking_id)
    result = await StockPicking.action_validate(env, picking_id)
    assert result["state"] == "done"

    from dodoo.addons.stock.models.stock_picking_type import StockPickingType

    stock_loc = (
        await StockPickingType.read(env, [_fixture["receipts_id"]], ["default_location_dest_id"])
    )[0]["default_location_dest_id"]
    forecast = await StockQuant.get_forecast(env, _fixture["product_id"], stock_loc)
    assert forecast["on_hand"] == 10


async def test_full_delivery_after_receipt(env, _fixture):
    from dodoo.addons.stock.models.stock_picking import StockPicking
    from dodoo.addons.stock.models.stock_quant import StockQuant

    receipt_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 10, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, receipt_id)
    await StockPicking.action_validate(env, receipt_id)

    delivery_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["delivery_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 4, "product_uom_id": _fixture["unit_id"]}],
    )
    confirm_state = await StockPicking.action_confirm(env, delivery_id)
    assert confirm_state == "ready"
    result = await StockPicking.action_validate(env, delivery_id)
    assert result["state"] == "done"
    assert result["backorder_id"] is None

    from dodoo.addons.stock.models.stock_picking_type import StockPickingType

    stock_loc = (
        await StockPickingType.read(env, [_fixture["receipts_id"]], ["default_location_dest_id"])
    )[0]["default_location_dest_id"]
    forecast = await StockQuant.get_forecast(env, _fixture["product_id"], stock_loc)
    assert forecast["on_hand"] == 6


async def test_partial_delivery_creates_backorder(env, _fixture):
    from dodoo.addons.stock.models.stock_picking import StockPicking

    receipt_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 6, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, receipt_id)
    await StockPicking.action_validate(env, receipt_id)

    delivery_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["delivery_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 20, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, delivery_id)
    result = await StockPicking.action_validate(env, delivery_id, create_backorder=True)
    assert result["backorder_id"] is not None

    from dodoo.addons.stock.models.stock_move import StockMove

    bo_move_ids = await StockMove.search(env, [["picking_id", "=", result["backorder_id"]]])
    bo_moves = await StockMove.read(env, bo_move_ids, ["product_uom_qty"])
    assert bo_moves[0]["product_uom_qty"] == 14


async def test_return_swaps_locations_and_restores_on_hand(env, _fixture):
    from dodoo.addons.stock.models.stock_picking import StockPicking
    from dodoo.addons.stock.models.stock_quant import StockQuant
    from dodoo.addons.stock.models.stock_picking_type import StockPickingType

    receipt_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 10, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, receipt_id)
    await StockPicking.action_validate(env, receipt_id)

    delivery_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["delivery_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 4, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, delivery_id)
    await StockPicking.action_validate(env, delivery_id)

    return_id = await StockPicking.action_return(env, delivery_id)
    await StockPicking.action_confirm(env, return_id)
    result = await StockPicking.action_validate(env, return_id)
    assert result["state"] == "done"

    stock_loc = (
        await StockPickingType.read(env, [_fixture["receipts_id"]], ["default_location_dest_id"])
    )[0]["default_location_dest_id"]
    forecast = await StockQuant.get_forecast(env, _fixture["product_id"], stock_loc)
    assert forecast["on_hand"] == 10


async def test_stale_validate_conflict(env, _fixture):
    from dodoo.addons.stock.models.stock_picking import StockPicking
    from dodoo.core.exceptions import DodooError

    receipt_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 5, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, receipt_id)
    await StockPicking.action_validate(env, receipt_id, expected_state="ready")
    with pytest.raises(DodooError, match="transfer_state_conflict"):
        await StockPicking.action_validate(env, receipt_id, expected_state="ready")
