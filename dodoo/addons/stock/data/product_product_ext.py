"""Extends `product`'s `product_product` table with a `tracking` column (D1) — the identical
`ALTER TABLE` idiom `account/data/account_data.py` uses on `res_partner`. Declared here (not on
`ProductProduct` itself) because `product` must carry no dependency on `stock`."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def add_tracking_column(env: Any) -> None:
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "ALTER TABLE product_product "
                "ADD COLUMN IF NOT EXISTS tracking VARCHAR(64) NOT NULL DEFAULT 'none'"
            )
        )
        await conn.commit()
