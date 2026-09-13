"""US7 — scrap confirmation (FR-067…070)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def _fixture(env, company_id):
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom
    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse
    from dodoo.addons.stock.models.stock_location import StockLocation
    from dodoo.addons.stock.models.stock_quant import StockQuant

    uom_cat = await UomCategory.create(env, {"name": "Scrap Unit"})
    unit = await UomUom.create(env, {"name": "Unit SC", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0})
    template = await ProductTemplate.create(
        env, {"name": "Scrap Product", "is_storable": True, "uom_id": unit, "company_id": company_id}
    )
    product_id = (await ProductProduct.search(env, [["template_id", "=", template]]))[0]

    wid = await StockWarehouse.create(env, {"name": "Scrap WH", "code": "SCWH", "company_id": company_id})
    wh = (await StockWarehouse.read(env, [wid], ["stock_location_id"]))[0]
    stock_loc = wh["stock_location_id"]

    scrap_loc = (
        await StockLocation.search(env, [["usage", "=", "inventory"]])
    )
    if not scrap_loc:
        scrap_loc_id = await StockLocation.create(env, {"name": "Scrap", "usage": "inventory"})
    else:
        scrap_loc_id = scrap_loc[0]

    await StockQuant.adjust_quantity(env, product_id, stock_loc, 10)

    return {"product_id": product_id, "stock_loc": stock_loc, "scrap_loc": scrap_loc_id}


async def test_scrap_reduces_source_and_increases_scrap_location(env, _fixture):
    from dodoo.addons.stock.models.stock_scrap import StockScrap
    from dodoo.addons.stock.models.stock_quant import StockQuant

    scrap_id = await StockScrap.create(
        env,
        {
            "product_id": _fixture["product_id"],
            "quantity": 2,
            "location_src_id": _fixture["stock_loc"],
            "location_dest_id": _fixture["scrap_loc"],
        },
    )
    result = await StockScrap.action_confirm(env, scrap_id)
    assert result["state"] == "done"

    src_forecast = await StockQuant.get_forecast(env, _fixture["product_id"], _fixture["stock_loc"])
    assert src_forecast["on_hand"] == 8


async def test_scrap_exceeding_on_hand_rejected(env, _fixture):
    from dodoo.addons.stock.models.stock_scrap import StockScrap

    scrap_id = await StockScrap.create(
        env,
        {
            "product_id": _fixture["product_id"],
            "quantity": 100,
            "location_src_id": _fixture["stock_loc"],
            "location_dest_id": _fixture["scrap_loc"],
        },
    )
    with pytest.raises(DodooError, match="scrap_qty_exceeds_on_hand"):
        await StockScrap.action_confirm(env, scrap_id)


async def test_done_scrap_is_immutable(env, _fixture):
    from dodoo.addons.stock.models.stock_scrap import StockScrap

    scrap_id = await StockScrap.create(
        env,
        {
            "product_id": _fixture["product_id"],
            "quantity": 1,
            "location_src_id": _fixture["stock_loc"],
            "location_dest_id": _fixture["scrap_loc"],
        },
    )
    await StockScrap.action_confirm(env, scrap_id)
    with pytest.raises(DodooError, match="scrap_locked_done"):
        await StockScrap.write(env, [scrap_id], {"quantity": 5})
