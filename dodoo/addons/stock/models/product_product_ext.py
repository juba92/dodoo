"""Read/write for the `tracking` column `stock` adds to `product_product` (D1).

Absent from ``ProductProduct._fields`` (the column is added by raw ``ALTER TABLE``, not a
declared ``Field``), so it is read/written here via raw SQL rather than through
``ProductProduct.read``/``.write`` (FR-043/045/046).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.exceptions import DodooError

if TYPE_CHECKING:
    from dodoo import Environment


async def get_tracking(env: Environment, product_id: int) -> str:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT tracking FROM product_product WHERE id = :id"), {"id": product_id}
        )
        r = row.fetchone()
        return r[0] if r else "none"


async def set_tracking(
    env: Environment, product_id: int, tracking: str, uid: int | None = None
) -> None:
    """Reject the change once the variant has any on-hand quantity or move-line history
    (FR-043) — a check only ``stock`` can make."""
    async with env.dml_conn() as conn:
        quant_row = await conn.execute(
            text(
                "SELECT 1 FROM stock_quant WHERE product_id = :p AND quantity <> 0 LIMIT 1"
            ),
            {"p": product_id},
        )
        if quant_row.fetchone():
            raise DodooError("tracking_locked_has_history")
        move_row = await conn.execute(
            text(
                "SELECT 1 FROM stock_move_line ml "
                "JOIN stock_move m ON m.id = ml.move_id "
                "WHERE m.product_id = :p LIMIT 1"
            ),
            {"p": product_id},
        )
        if move_row.fetchone():
            raise DodooError("tracking_locked_has_history")
        await conn.execute(
            text("UPDATE product_product SET tracking = :t WHERE id = :id"),
            {"t": tracking, "id": product_id},
        )
        await conn.commit()
