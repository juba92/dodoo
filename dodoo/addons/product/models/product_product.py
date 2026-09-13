"""``product.product`` — a sellable/stockable variant (FR-006/007).

``tracking`` (lot/serial mode) is added to this table by ``stock`` and ``stock_avg_cost`` by
``stock_account``, both via ``ALTER TABLE`` (D1) — neither is declared here.
"""

from __future__ import annotations

import itertools
import logging
from typing import TYPE_CHECKING, Any

from dodoo.core.fields import Char, Many2many, Many2one, Monetary
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class ProductProduct(BaseModel):
    _name = "product.product"

    template_id = Many2one("product.template", required=True)
    barcode = Char(size=64)
    price_extra = Monetary()
    attribute_value_ids = Many2many(
        "product.attribute.value",
        relation_table="product_product_attribute_value_rel",
        column1="product_id",
        column2="value_id",
    )

    @classmethod
    async def generate_variants(cls, env: Environment, template_id: int) -> list[int]:
        """Generate one variant per element of the Cartesian product of the template's
        attribute-line values (FR-006), skipping combinations that already have a variant."""
        from dodoo.addons.product.models.product_attribute import (
            ProductTemplateAttributeLine,
        )

        line_ids = await ProductTemplateAttributeLine.search(
            env, [["template_id", "=", template_id]]
        )
        lines = (
            await ProductTemplateAttributeLine.read(
                env, line_ids, ["attribute_id", "value_ids"]
            )
            if line_ids
            else []
        )

        existing_ids = await cls.search(env, [["template_id", "=", template_id]])
        existing_records = (
            await cls.read(env, existing_ids, ["attribute_value_ids"])
            if existing_ids
            else []
        )

        if not lines:
            if not existing_records:
                await cls.create(env, {"template_id": template_id})
            return await cls.search(env, [["template_id", "=", template_id]])

        # A template moving from zero to one-or-more attribute lines makes its previous
        # implicit (no-attribute) variant stale; remove it if nothing else references it yet.
        for rec in existing_records:
            if not rec.get("attribute_value_ids"):
                try:
                    await cls.unlink(env, [rec["id"]])
                except Exception:  # noqa: BLE001 — FK-restricted (already has history); keep it
                    _log.debug(
                        "product.product %s: implicit variant kept (in use)", rec["id"]
                    )

        existing_ids = await cls.search(env, [["template_id", "=", template_id]])
        existing_records = (
            await cls.read(env, existing_ids, ["attribute_value_ids"])
            if existing_ids
            else []
        )
        existing_combos = {
            frozenset(r["attribute_value_ids"]) for r in existing_records
        }

        value_lists = [line["value_ids"] for line in lines]
        for combo in itertools.product(*value_lists):
            key = frozenset(combo)
            if key in existing_combos:
                continue
            await cls.create(
                env,
                {"template_id": template_id, "attribute_value_ids": list(combo)},
            )
            existing_combos.add(key)

        return await cls.search(env, [["template_id", "=", template_id]])
