"""US8 — standard and average costing valuation (ADR-033/034)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def _fixture(env, company_id):
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom
    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse
    from sqlalchemy import text

    cat = await ProductCategory.create(env, {"name": "Valuation Cat"})
    uom_cat = await UomCategory.create(env, {"name": "Valuation Unit"})
    unit = await UomUom.create(env, {"name": "Unit VAL", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0})
    template = await ProductTemplate.create(
        env,
        {
            "name": "Valuation Product",
            "category_id": cat,
            "is_storable": True,
            "uom_id": unit,
            "standard_price": 10,
            "company_id": company_id,
        },
    )
    product_id = (await ProductProduct.search(env, [["template_id", "=", template]]))[0]

    wid = await StockWarehouse.create(env, {"name": "Valuation WH", "code": "VLWH", "company_id": company_id})
    wh = (await StockWarehouse.read(env, [wid], ["stock_location_id"]))[0]

    from dodoo.addons.stock.models.stock_picking_type import StockPickingType
    from dodoo.addons.stock.validators import and_domain

    receipts_id = (
        await StockPickingType.search(env, and_domain(["warehouse_id", "=", wid], ["name", "=", "Receipts"]))
    )[0]
    delivery_id = (
        await StockPickingType.search(env, and_domain(["warehouse_id", "=", wid], ["name", "=", "Delivery Orders"]))
    )[0]

    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "UPDATE product_category SET costing_method='standard', "
                "property_stock_valuation_account_id=(SELECT id FROM account_account WHERE code='1100' AND company_id=:c LIMIT 1), "
                "property_stock_input_account_id=(SELECT id FROM account_account WHERE code='1101' AND company_id=:c LIMIT 1), "
                "property_stock_output_account_id=(SELECT id FROM account_account WHERE code='1102' AND company_id=:c LIMIT 1) "
                "WHERE id=:cat"
            ),
            {"c": company_id, "cat": cat},
        )
        await conn.commit()

    return {"product_id": product_id, "category_id": cat, "unit_id": unit, "receipts_id": receipts_id, "delivery_id": delivery_id}


async def test_standard_costing_receipt_creates_layer_and_journal_entry(env, _fixture):
    from dodoo.addons.stock.models.stock_picking import StockPicking
    from dodoo.addons.stock_account.models.stock_valuation_layer import StockValuationLayer

    receipt_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [{"product_id": _fixture["product_id"], "product_uom_qty": 5, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, receipt_id)
    await StockPicking.action_validate(env, receipt_id)

    layer_ids = await StockValuationLayer.search(env, [["product_id", "=", _fixture["product_id"]]])
    assert len(layer_ids) == 1
    layer = (await StockValuationLayer.read(env, layer_ids, ["value", "unit_cost", "account_move_id"]))[0]
    assert layer["value"] == 50
    assert layer["unit_cost"] == 10
    assert layer["account_move_id"] is not None

    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    move = (await AccountMove.read(env, [layer["account_move_id"]], ["state"]))[0]
    assert move["state"] == "posted"

    line_ids = await AccountMoveLine.search(env, [["move_id", "=", layer["account_move_id"]]])
    lines = await AccountMoveLine.read(env, line_ids, ["debit", "credit"])
    assert sum(l["debit"] for l in lines) == sum(l["credit"] for l in lines) == 50


async def test_non_storable_product_produces_no_layer(env, company_id, _fixture):
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.stock.models.stock_picking import StockPicking
    from dodoo.addons.stock_account.models.stock_valuation_layer import StockValuationLayer

    svc_template = await ProductTemplate.create(
        env,
        {"name": "Non Storable", "is_storable": False, "uom_id": _fixture["unit_id"], "company_id": company_id},
    )
    svc_product_id = (await ProductProduct.search(env, [["template_id", "=", svc_template]]))[0]

    receipt_id = await StockPicking.create_with_moves(
        env,
        {"picking_type_id": _fixture["receipts_id"]},
        [{"product_id": svc_product_id, "product_uom_qty": 5, "product_uom_id": _fixture["unit_id"]}],
    )
    await StockPicking.action_confirm(env, receipt_id)
    await StockPicking.action_validate(env, receipt_id)

    layer_ids = await StockValuationLayer.search(env, [["product_id", "=", svc_product_id]])
    assert layer_ids == []
