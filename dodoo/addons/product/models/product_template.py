"""``product.template`` — the shared definition of a sellable/stockable thing (FR-004/008)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Many2one, Monetary, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

PRODUCT_TYPE_CHOICES = [
    ("goods", "Goods"),
    ("service", "Service"),
]


class ProductTemplate(BaseModel):
    _name = "product.template"

    name = Char(size=256, required=True)
    barcode = Char(size=64)
    category_id = Many2one("product.category")
    product_type = Selection(PRODUCT_TYPE_CHOICES, default="goods")
    is_storable = Boolean(default=False)
    uom_id = Many2one("uom.uom", required=True)
    purchase_uom_id = Many2one("uom.uom")
    list_price = Monetary()
    standard_price = Monetary()
    company_id = Many2one("res.company")
    active = Boolean(default=True)

    @classmethod
    async def _assert_uom_categories_match(
        cls, env: Environment, uom_id: int | None, purchase_uom_id: int | None
    ) -> None:
        if not uom_id or not purchase_uom_id:
            return
        from dodoo.addons.product.models.uom import UomUom

        rows = await UomUom.read(env, [uom_id, purchase_uom_id], ["category_id"])
        by_id = {r["id"]: r["category_id"] for r in rows}
        if by_id.get(uom_id) != by_id.get(purchase_uom_id):
            raise DodooError("uom_category_mismatch")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        vals = dict(vals)
        if vals.get("product_type") == "service":
            vals["is_storable"] = False
        await cls._assert_uom_categories_match(
            env, vals.get("uom_id"), vals.get("purchase_uom_id")
        )
        template_id = await super().create(env, vals)
        # Templates with no attribute lines get exactly one implicit variant (FR-007).
        from dodoo.addons.product.models.product_product import ProductProduct

        await ProductProduct.create(env, {"template_id": template_id})
        return template_id

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        vals = dict(vals)
        if vals.get("product_type") == "service":
            vals["is_storable"] = False
        if "uom_id" in vals or "purchase_uom_id" in vals:
            for tid in ids:
                cur = await super().read(env, [tid], ["uom_id", "purchase_uom_id"])
                if cur:
                    uom_id = vals.get("uom_id", cur[0]["uom_id"])
                    purchase_uom_id = vals.get("purchase_uom_id", cur[0]["purchase_uom_id"])
                    await cls._assert_uom_categories_match(env, uom_id, purchase_uom_id)
        return await super().write(env, ids, vals)
