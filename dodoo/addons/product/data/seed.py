"""``seed_product_data`` — the Product addon's ``post_install`` entry point (FR-089).

Order: ``ir_model`` rows (so ``ir.rule.model_id`` resolves, seeded by ``stock``'s record rules
which target these models) → indexes → sample data. Every step is idempotent.
"""

from __future__ import annotations

import logging
from typing import Any

from dodoo.addons.product.data.indexes import ensure_indexes
from dodoo.addons.product.data.ir_model_sync import sync_ir_model

_log = logging.getLogger(__name__)

IR_MODELS: list[tuple[str, str]] = [
    ("product.category", "product_category"),
    ("uom.category", "uom_category"),
    ("uom.uom", "uom_uom"),
    ("product.template", "product_template"),
    ("product.attribute", "product_attribute"),
    ("product.attribute.value", "product_attribute_value"),
    ("product.template.attribute.line", "product_template_attribute_line"),
    ("product.product", "product_product"),
]

# PERF-001 covering indexes.
INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_product_product_template ON product_product (template_id)",
    "CREATE INDEX IF NOT EXISTS idx_product_template_search ON product_template (company_id, category_id, product_type)",
    "CREATE INDEX IF NOT EXISTS idx_product_template_barcode ON product_template (barcode)",
    "CREATE INDEX IF NOT EXISTS idx_product_product_barcode ON product_product (barcode)",
]


async def _seed_sample_data(env: Any) -> None:
    from dodoo.addons.product.models.product_category import ProductCategory
    from dodoo.addons.product.models.product_template import ProductTemplate
    from dodoo.addons.product.models.uom import UomUom, UomCategory

    existing = await UomCategory.search(env, [["name", "=", "Unit"]])
    if existing:
        _log.info("product: sample data already seeded; skipping")
        return

    unit_cat = await UomCategory.create(env, {"name": "Unit"})
    unit_id = await UomUom.create(
        env, {"name": "Unit", "category_id": unit_cat, "uom_type": "reference", "ratio": 1.0}
    )
    await UomUom.create(
        env,
        {"name": "Dozen", "category_id": unit_cat, "uom_type": "bigger", "ratio": 12.0},
    )

    weight_cat = await UomCategory.create(env, {"name": "Weight"})
    await UomUom.create(
        env,
        {
            "name": "Kilogram",
            "category_id": weight_cat,
            "uom_type": "reference",
            "ratio": 1.0,
        },
    )
    await UomUom.create(
        env,
        {"name": "Gram", "category_id": weight_cat, "uom_type": "smaller", "ratio": 0.001},
    )

    goods_cat = await ProductCategory.create(env, {"name": "Goods"})
    services_cat = await ProductCategory.create(env, {"name": "Services"})

    await ProductTemplate.create(
        env,
        {
            "name": "Sample Tracked Good",
            "category_id": goods_cat,
            "product_type": "goods",
            "is_storable": True,
            "uom_id": unit_id,
            "list_price": 10,
            "standard_price": 5,
        },
    )
    await ProductTemplate.create(
        env,
        {
            "name": "Sample Untracked Good",
            "category_id": goods_cat,
            "product_type": "goods",
            "is_storable": False,
            "uom_id": unit_id,
            "list_price": 2,
            "standard_price": 1,
        },
    )
    await ProductTemplate.create(
        env,
        {
            "name": "Sample Service",
            "category_id": services_cat,
            "product_type": "service",
            "is_storable": False,
            "uom_id": unit_id,
            "list_price": 50,
        },
    )


async def seed_product_data(env: Any) -> None:
    await sync_ir_model(env, IR_MODELS)
    await ensure_indexes(env, INDEXES)
    await _seed_sample_data(env)
    _log.info("product: seed complete (%d models, %d indexes)", len(IR_MODELS), len(INDEXES))
