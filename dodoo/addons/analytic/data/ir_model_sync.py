from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def sync_ir_model(env: Any, models: list[tuple[str, str]]) -> None:
    """``models`` is a list of ``(model_name, table_name)`` pairs."""
    async with env.dml_conn() as conn:
        for name, table in models:
            await conn.execute(
                text(
                    "INSERT INTO ir_model (name, table_name) VALUES (:n, :t) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"n": name, "t": table},
            )
        await conn.commit()
