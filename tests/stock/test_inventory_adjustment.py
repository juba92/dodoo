"""US4 — physical inventory count application (FR-037…042)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def _fixture(env, company_id):
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom
    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse
    from dodoo.addons.stock.models.stock_quant import StockQuant

    uom_cat = await UomCategory.create(env, {"name": "Count Unit"})
    unit = await UomUom.create(env, {"name": "Unit CNT", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0})
    template = await ProductTemplate.create(env, {"name": "Count Product", "is_storable": True, "uom_id": unit, "company_id": company_id})
    product_id = (await ProductProduct.search(env, [["template_id", "=", template]]))[0]

    wid = await StockWarehouse.create(env, {"name": "Count WH", "code": "CNWH", "company_id": company_id})
    wh = (await StockWarehouse.read(env, [wid], ["stock_location_id"]))[0]
    stock_loc = wh["stock_location_id"]

    quant_id = await StockQuant.adjust_quantity(env, product_id, stock_loc, 10)
    return {"product_id": product_id, "stock_loc": stock_loc, "quant_id": quant_id}


async def test_lower_count_decreases_on_hand(env, _fixture):
    from dodoo.addons.stock.models.stock_quant import StockQuant

    await StockQuant.write(env, [_fixture["quant_id"]], {"counted_quantity": 8})
    result = await StockQuant.apply_count(env, [_fixture["quant_id"]])
    assert result["applied"] == 1

    rec = (await StockQuant.read(env, [_fixture["quant_id"]], ["quantity"]))[0]
    assert rec["quantity"] == 8


async def test_equal_count_is_a_noop(env, _fixture):
    from dodoo.addons.stock.models.stock_quant import StockQuant

    await StockQuant.write(env, [_fixture["quant_id"]], {"counted_quantity": 10})
    result = await StockQuant.apply_count(env, [_fixture["quant_id"]])
    assert result["applied"] == 0
    assert result["skipped"] == 1


async def test_higher_count_increases_on_hand_and_logs(env, _fixture):
    from dodoo.addons.stock.models.stock_quant import StockQuant
    from dodoo.addons.stock.models.stock_inventory_adjustment import (
        StockInventoryAdjustmentLog,
    )

    await StockQuant.write(env, [_fixture["quant_id"]], {"counted_quantity": 15})
    result = await StockQuant.apply_count(env, [_fixture["quant_id"]], uid=1)
    assert result["applied"] == 1

    log = (await StockInventoryAdjustmentLog.read(env, result["log_ids"], ["qty_before", "qty_after", "difference"]))[0]
    assert log["qty_before"] == 10
    assert log["qty_after"] == 15
    assert log["difference"] == 5
