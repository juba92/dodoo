"""US6 — route rule-chain validation and reordering-rule replenishment (ADR-032)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def _fixture(env, company_id):
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom
    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse

    uom_cat = await UomCategory.create(env, {"name": "Order Unit"})
    unit = await UomUom.create(env, {"name": "Unit ORD", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0})
    template = await ProductTemplate.create(env, {"name": "Order Product", "is_storable": True, "uom_id": unit, "company_id": company_id})
    product_id = (await ProductProduct.search(env, [["template_id", "=", template]]))[0]

    wid = await StockWarehouse.create(env, {"name": "Order WH", "code": "ORWH", "company_id": company_id})
    wh = (await StockWarehouse.read(env, [wid], ["stock_location_id"]))[0]
    return {"product_id": product_id, "stock_loc": wh["stock_location_id"], "wid": wid}


async def test_rule_self_reference_rejected(env, _fixture):
    from dodoo.addons.stock.models.stock_route import StockRoute, StockRule

    route_id = await StockRoute.create(env, {"name": "Self Ref Route"})
    with pytest.raises(DodooError, match="rule_self_reference"):
        await StockRule.create(
            env,
            {
                "route_id": route_id,
                "location_src_id": _fixture["stock_loc"],
                "location_dest_id": _fixture["stock_loc"],
                "picking_type_id": 1,
            },
        )


async def test_reordering_below_minimum_triggers_fallback_receipt(env, _fixture):
    from dodoo.addons.stock.models.stock_orderpoint import StockWarehouseOrderpoint
    from dodoo.addons.stock.models.stock_quant import StockQuant

    await StockQuant.adjust_quantity(env, _fixture["product_id"], _fixture["stock_loc"], 3)

    op_id = await StockWarehouseOrderpoint.create(
        env,
        {
            "product_id": _fixture["product_id"],
            "location_id": _fixture["stock_loc"],
            "product_min_qty": 5,
            "product_max_qty": 20,
            "qty_multiple": 1,
        },
    )
    result = await StockWarehouseOrderpoint.run_reordering(env, [op_id])
    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["picking_ids"]


async def test_reordering_skips_when_already_covered(env, _fixture):
    from dodoo.addons.stock.models.stock_orderpoint import StockWarehouseOrderpoint
    from dodoo.addons.stock.models.stock_quant import StockQuant

    await StockQuant.adjust_quantity(env, _fixture["product_id"], _fixture["stock_loc"], 3)
    op_id = await StockWarehouseOrderpoint.create(
        env,
        {
            "product_id": _fixture["product_id"],
            "location_id": _fixture["stock_loc"],
            "product_min_qty": 5,
            "product_max_qty": 20,
        },
    )
    first = await StockWarehouseOrderpoint.run_reordering(env, [op_id])
    assert first["triggered"]
    second = await StockWarehouseOrderpoint.run_reordering(env, [op_id])
    assert second["skipped_covered"] == [op_id]
    assert not second["triggered"]
