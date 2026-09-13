"""Extends `product`'s `product_product` table with the average-costing running value (D1)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def add_stock_avg_cost_column(env: Any) -> None:
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "ALTER TABLE product_product "
                "ADD COLUMN IF NOT EXISTS stock_avg_cost NUMERIC(20,6) NOT NULL DEFAULT 0"
            )
        )
        await conn.commit()
