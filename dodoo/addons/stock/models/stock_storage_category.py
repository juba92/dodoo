"""``stock.storage.category`` — capacity constraints on locations (ADR-031, FR-055)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.fields import Char, Float, Integer, Many2many, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

ALLOW_NEW_PRODUCT_CHOICES = [
    ("always", "Always"),
    ("same_product", "Only Same Product"),
    ("same_lot", "Only Same Lot"),
]


class StockStorageCategory(BaseModel):
    _name = "stock.storage.category"

    name = Char(size=128, required=True)
    max_weight = Float()
    max_packages = Integer()
    allow_new_product = Selection(ALLOW_NEW_PRODUCT_CHOICES, default="always")
    location_ids = Many2many(
        "stock.location",
        relation_table="stock_storage_category_location_rel",
        column1="category_id",
        column2="location_id",
    )

    @classmethod
    async def has_capacity(
        cls,
        env: Environment,
        location_id: int,
        incoming_qty: float,
        incoming_product_id: int | None = None,
    ) -> bool:
        """True when ``location_id`` has no storage category (unlimited) or the incoming
        quantity/product fits within every category assigned to it (ADR-031)."""
        async with env.dml_conn() as conn:
            cat_row = await conn.execute(
                text(
                    "SELECT category_id FROM stock_storage_category_location_rel "
                    "WHERE location_id = :l"
                ),
                {"l": location_id},
            )
            cat_ids = [r[0] for r in cat_row]
        if not cat_ids:
            return True
        cats = await cls.read(env, cat_ids, ["max_packages", "allow_new_product"])
        async with env.dml_conn() as conn:
            existing_row = await conn.execute(
                text(
                    "SELECT COUNT(DISTINCT package_id), COUNT(DISTINCT product_id) "
                    "FROM stock_quant WHERE location_id = :l AND quantity <> 0"
                ),
                {"l": location_id},
            )
            package_count, product_count = existing_row.fetchone()
            has_other_product = False
            if incoming_product_id is not None:
                other_row = await conn.execute(
                    text(
                        "SELECT 1 FROM stock_quant WHERE location_id = :l AND quantity <> 0 "
                        "AND product_id <> :p LIMIT 1"
                    ),
                    {"l": location_id, "p": incoming_product_id},
                )
                has_other_product = other_row.fetchone() is not None

        for cat in cats:
            if cat["max_packages"] and package_count >= cat["max_packages"]:
                return False
            if cat["allow_new_product"] == "same_product" and has_other_product:
                return False
        return True
