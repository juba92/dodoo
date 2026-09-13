"""US6 — putaway rule resolution and storage-category capacity (ADR-031)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def _fixture(env, company_id):
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom
    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse
    from dodoo.addons.stock.models.stock_location import StockLocation

    cat = await ProductCategory.create(env, {"name": "Putaway Cat"})
    uom_cat = await UomCategory.create(env, {"name": "Putaway Unit"})
    unit = await UomUom.create(env, {"name": "Unit PW", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0})
    template = await ProductTemplate.create(
        env, {"name": "Putaway Product", "category_id": cat, "product_type": "goods", "is_storable": True, "uom_id": unit, "company_id": company_id}
    )
    product_id = (await ProductProduct.search(env, [["template_id", "=", template]]))[0]

    wid = await StockWarehouse.create(env, {"name": "Putaway WH", "code": "PWWH", "company_id": company_id})
    wh = (await StockWarehouse.read(env, [wid], ["stock_location_id"]))[0]
    stock_loc = wh["stock_location_id"]

    bin_a = await StockLocation.create(env, {"name": "Bin A", "parent_id": stock_loc, "usage": "internal", "warehouse_id": wid, "company_id": company_id})
    bin_b = await StockLocation.create(env, {"name": "Bin B", "parent_id": stock_loc, "usage": "internal", "warehouse_id": wid, "company_id": company_id})

    return {"product_id": product_id, "stock_loc": stock_loc, "bin_a": bin_a, "bin_b": bin_b, "wid": wid}


async def test_no_rule_leaves_destination_unchanged(env, _fixture):
    from dodoo.addons.stock.models.stock_putaway_rule import StockPutawayRule

    dest = await StockPutawayRule.resolve_destination(env, _fixture["product_id"], _fixture["stock_loc"])
    assert dest == _fixture["stock_loc"]


async def test_product_rule_redirects_destination(env, _fixture):
    from dodoo.addons.stock.models.stock_putaway_rule import StockPutawayRule

    await StockPutawayRule.create(
        env,
        {
            "location_src_id": _fixture["stock_loc"],
            "product_id": _fixture["product_id"],
            "location_dest_id": _fixture["bin_a"],
        },
    )
    dest = await StockPutawayRule.resolve_destination(env, _fixture["product_id"], _fixture["stock_loc"])
    assert dest == _fixture["bin_a"]


async def test_storage_category_capacity_redirects_to_next_rule(env, _fixture):
    from dodoo.addons.stock.models.stock_putaway_rule import StockPutawayRule
    from dodoo.addons.stock.models.stock_storage_category import StockStorageCategory
    from dodoo.addons.stock.models.stock_quant import StockQuant

    cat_id = await StockStorageCategory.create(
        env,
        {
            "name": "One Product Only",
            "allow_new_product": "same_product",
            "location_ids": [_fixture["bin_a"]],
        },
    )
    # Occupy bin_a with a DIFFERENT product so it no longer has capacity for ours.
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomUom
    from dodoo.addons.product.models.product_product import ProductProduct

    other_template = await ProductTemplate.create(
        env,
        {
            "name": "Other Product",
            "uom_id": _fixture.get("unit_id")
            or (await UomUom.search(env, [["name", "=", "Unit PW"]]))[0],
            "is_storable": True,
        },
    )
    other_product_id = (await ProductProduct.search(env, [["template_id", "=", other_template]]))[0]
    await StockQuant.adjust_quantity(env, other_product_id, _fixture["bin_a"], 5)

    await StockPutawayRule.create(
        env,
        {
            "location_src_id": _fixture["stock_loc"],
            "product_id": _fixture["product_id"],
            "location_dest_id": _fixture["bin_a"],
            "sequence": 1,
        },
    )
    await StockPutawayRule.create(
        env,
        {
            "location_src_id": _fixture["stock_loc"],
            "product_id": _fixture["product_id"],
            "location_dest_id": _fixture["bin_b"],
            "sequence": 2,
        },
    )

    dest = await StockPutawayRule.resolve_destination(env, _fixture["product_id"], _fixture["stock_loc"])
    assert dest == _fixture["bin_b"]
