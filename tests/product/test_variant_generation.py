"""US1 — variant Cartesian-product generation and idempotent regeneration (FR-006)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def _base(env, company_id):
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomCategory, UomUom

    cat = await ProductCategory.create(env, {"name": "Variant Test Category"})
    uom_cat = await UomCategory.create(env, {"name": "Variant Test Unit"})
    unit = await UomUom.create(
        env, {"name": "Unit VT", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0}
    )
    template = await ProductTemplate.create(
        env,
        {
            "name": "T-Shirt Test",
            "category_id": cat,
            "product_type": "goods",
            "is_storable": True,
            "uom_id": unit,
            "company_id": company_id,
        },
    )
    return {"template_id": template}


async def test_template_with_no_lines_has_one_implicit_variant(env, _base):
    from dodoo.addons.product.models.product_product import ProductProduct

    ids = await ProductProduct.search(env, [["template_id", "=", _base["template_id"]]])
    assert len(ids) == 1
    rec = (await ProductProduct.read(env, ids, ["attribute_value_ids"]))[0]
    assert rec["attribute_value_ids"] == []


async def test_two_attributes_generate_cartesian_product(env, _base):
    from dodoo.addons.product.models.product_attribute import (
        ProductAttribute,
        ProductAttributeValue,
    )
    from dodoo.addons.product.models.product_product import ProductProduct

    color = await ProductAttribute.create(env, {"name": "Color VT"})
    red = await ProductAttributeValue.create(env, {"attribute_id": color, "name": "Red"})
    blue = await ProductAttributeValue.create(env, {"attribute_id": color, "name": "Blue"})
    size = await ProductAttribute.create(env, {"name": "Size VT"})
    s = await ProductAttributeValue.create(env, {"attribute_id": size, "name": "S"})
    m = await ProductAttributeValue.create(env, {"attribute_id": size, "name": "M"})

    from dodoo.addons.product.models.product_attribute import (
        ProductTemplateAttributeLine,
    )

    await ProductTemplateAttributeLine.create(
        env,
        {"template_id": _base["template_id"], "attribute_id": color, "value_ids": [red, blue]},
    )
    await ProductTemplateAttributeLine.create(
        env, {"template_id": _base["template_id"], "attribute_id": size, "value_ids": [s, m]}
    )

    variant_ids = await ProductProduct.generate_variants(env, _base["template_id"])
    assert len(variant_ids) == 4

    combos = set()
    for rec in await ProductProduct.read(env, variant_ids, ["attribute_value_ids"]):
        combos.add(frozenset(rec["attribute_value_ids"]))
    assert combos == {
        frozenset([red, s]),
        frozenset([red, m]),
        frozenset([blue, s]),
        frozenset([blue, m]),
    }


async def test_regeneration_is_idempotent(env, _base):
    from dodoo.addons.product.models.product_attribute import (
        ProductAttribute,
        ProductAttributeValue,
        ProductTemplateAttributeLine,
    )
    from dodoo.addons.product.models.product_product import ProductProduct

    color = await ProductAttribute.create(env, {"name": "Color VT2"})
    red = await ProductAttributeValue.create(env, {"attribute_id": color, "name": "Red2"})
    await ProductTemplateAttributeLine.create(
        env, {"template_id": _base["template_id"], "attribute_id": color, "value_ids": [red]}
    )

    first = await ProductProduct.generate_variants(env, _base["template_id"])
    second = await ProductProduct.generate_variants(env, _base["template_id"])
    assert set(first) == set(second)
