"""``stock.putaway.rule`` — redirects an arriving product to a specific destination
(ADR-031, FR-056…058)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.addons.stock.validators import and_domain
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Integer, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class StockPutawayRule(BaseModel):
    _name = "stock.putaway.rule"

    location_src_id = Many2one("stock.location", required=True)
    product_id = Many2one("product.product")
    category_id = Many2one("product.category")
    location_dest_id = Many2one("stock.location", required=True)
    sequence = Integer(default=10)

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        if bool(vals.get("product_id")) == bool(vals.get("category_id")):
            raise DodooError("putaway_rule_needs_exactly_one_of_product_or_category")
        return await super().create(env, vals)

    @classmethod
    async def resolve_destination(
        cls, env: Environment, product_id: int, source_location_id: int
    ) -> int:
        """Redirect a move line's destination per the first eligible rule with capacity
        (ADR-031); returns ``source_location_id`` unchanged when no rule applies or none of
        its destinations currently have capacity."""
        from dodoo.addons.product.models.product_product import ProductProduct
        from dodoo.addons.stock.models.stock_storage_category import StockStorageCategory

        template_id = (
            await ProductProduct.read(env, [product_id], ["template_id"])
        )[0]["template_id"]
        from dodoo.addons.product.models.product_template import ProductTemplate

        category_id = (
            await ProductTemplate.read(env, [template_id], ["category_id"])
        )[0]["category_id"]

        product_rule_ids = await cls.search(
            env,
            and_domain(
                ["location_src_id", "=", source_location_id], ["product_id", "=", product_id]
            ),
        )
        category_rule_ids = (
            await cls.search(
                env,
                and_domain(
                    ["location_src_id", "=", source_location_id],
                    ["category_id", "=", category_id],
                ),
            )
            if category_id
            else []
        )
        ordered_ids = list(product_rule_ids) + list(category_rule_ids)
        if not ordered_ids:
            return source_location_id

        rules = await cls.read(env, ordered_ids, ["location_dest_id", "sequence"])
        rules.sort(key=lambda r: r["sequence"])
        for rule in rules:
            if await StockStorageCategory.has_capacity(
                env, rule["location_dest_id"], 1, product_id
            ):
                return rule["location_dest_id"]
        return source_location_id
