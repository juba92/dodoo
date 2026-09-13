"""US1 — category hierarchy, shared-vs-scoped catalog visibility, and untracked/service
products carrying no stock-tracking fields (FR-001/008/010).

Company-scope *enforcement* (the `ir.rule` domain) is seeded by `stock/data/rules.py` and is
exercised in `tests/stock/test_access_rules.py` once `stock` is installed; this file only checks
the data shape `product` itself is responsible for.
"""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


async def test_category_cycle_rejected(env):
    from dodoo.addons.product.models.product_category import ProductCategory

    parent = await ProductCategory.create(env, {"name": "Cycle Parent"})
    child = await ProductCategory.create(env, {"name": "Cycle Child", "parent_id": parent})
    with pytest.raises(DodooError, match="category_cycle"):
        await ProductCategory.write(env, [parent], {"parent_id": child})


async def test_category_hierarchy_is_navigable(env):
    from dodoo.addons.product.models.product_category import ProductCategory

    parent = await ProductCategory.create(env, {"name": "Hierarchy Parent"})
    child = await ProductCategory.create(env, {"name": "Hierarchy Child", "parent_id": parent})
    rec = (await ProductCategory.read(env, [child], ["parent_id"]))[0]
    assert rec["parent_id"] == parent


async def test_nullable_company_id_means_shared(env):
    from dodoo.addons.product.models.product_category import ProductCategory

    shared = await ProductCategory.create(env, {"name": "Shared Category"})
    rec = (await ProductCategory.read(env, [shared], ["company_id"]))[0]
    assert rec["company_id"] is None


async def test_service_and_untracked_goods_have_no_stock_fields(env):
    from dodoo.addons.product.models.product_template import ProductTemplate

    field_names = set(ProductTemplate._fields.keys())
    # No location/quantity concept belongs to the product addon at all.
    assert "quantity" not in field_names
    assert "location_id" not in field_names
    # `is_storable` is forced off for services.
    from dodoo.addons.product.models.uom import UomCategory, UomUom

    uom_cat = await UomCategory.create(env, {"name": "Svc Unit"})
    unit = await UomUom.create(
        env, {"name": "Unit Svc", "category_id": uom_cat, "uom_type": "reference", "ratio": 1.0}
    )
    svc = await ProductTemplate.create(
        env,
        {
            "name": "A Service",
            "product_type": "service",
            "is_storable": True,  # ignored — forced False for services
            "uom_id": unit,
        },
    )
    rec = (await ProductTemplate.read(env, [svc], ["is_storable"]))[0]
    assert rec["is_storable"] is False
