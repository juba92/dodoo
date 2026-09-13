"""``stock.route`` / ``stock.rule`` — supply-path chains (ADR-032, FR-060…062)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Integer, Many2many, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

RULE_ACTION_CHOICES = [
    ("move", "Move Within Warehouse"),
    ("resupply", "Resupply From Another Warehouse"),
]


class StockRoute(BaseModel):
    _name = "stock.route"

    name = Char(size=128, required=True)
    product_ids = Many2many(
        "product.product",
        relation_table="stock_route_product_rel",
        column1="route_id",
        column2="product_id",
    )
    category_ids = Many2many(
        "product.category",
        relation_table="stock_route_category_rel",
        column1="route_id",
        column2="category_id",
    )
    warehouse_ids = Many2many(
        "stock.warehouse",
        relation_table="stock_route_warehouse_rel",
        column1="route_id",
        column2="warehouse_id",
    )

    @classmethod
    async def get_applicable_route(
        cls, env: Environment, product_id: int, warehouse_id: int
    ) -> int | None:
        """Product-level override → category-level → warehouse default (ADR-032)."""
        from dodoo.addons.product.models.product_product import ProductProduct
        from dodoo.addons.product.models.product_template import ProductTemplate

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT route_id FROM stock_route_product_rel WHERE product_id = :p LIMIT 1"),
                {"p": product_id},
            )
            r = row.fetchone()
            if r:
                return r[0]

        template_id = (
            await ProductProduct.read(env, [product_id], ["template_id"])
        )[0]["template_id"]
        category_id = (
            await ProductTemplate.read(env, [template_id], ["category_id"])
        )[0]["category_id"]
        if category_id:
            async with env.dml_conn() as conn:
                row = await conn.execute(
                    text(
                        "SELECT route_id FROM stock_route_category_rel WHERE category_id = :c LIMIT 1"
                    ),
                    {"c": category_id},
                )
                r = row.fetchone()
                if r:
                    return r[0]

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT route_id FROM stock_route_warehouse_rel WHERE warehouse_id = :w LIMIT 1"
                ),
                {"w": warehouse_id},
            )
            r = row.fetchone()
            return r[0] if r else None


class StockRule(BaseModel):
    _name = "stock.rule"

    route_id = Many2one("stock.route", required=True)
    sequence = Integer(default=10)
    action = Selection(RULE_ACTION_CHOICES, default="move")
    location_src_id = Many2one("stock.location", required=True)
    location_dest_id = Many2one("stock.location", required=True)
    picking_type_id = Many2one("stock.picking.type", required=True)

    @classmethod
    async def _assert_no_self_reference(
        cls, env: Environment, route_id: int, location_src_id: int, location_dest_id: int
    ) -> None:
        """A rule's destination must not equal its own source, directly or transitively,
        within the same route (FR-062)."""
        if location_src_id == location_dest_id:
            raise DodooError("rule_self_reference")
        rule_ids = await cls.search(env, [["route_id", "=", route_id]])
        rules = (
            await cls.read(env, rule_ids, ["location_src_id", "location_dest_id"])
            if rule_ids
            else []
        )
        # Walk the chain starting at the new rule's destination; if we ever reach its
        # source, the route has a cycle.
        by_src = {r["location_src_id"]: r["location_dest_id"] for r in rules}
        current = location_dest_id
        seen = {location_dest_id}
        while current in by_src:
            nxt = by_src[current]
            if nxt == location_src_id:
                raise DodooError("rule_self_reference")
            if nxt in seen:
                break
            seen.add(nxt)
            current = nxt

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        await cls._assert_no_self_reference(
            env, vals["route_id"], vals["location_src_id"], vals["location_dest_id"]
        )
        return await super().create(env, vals)
