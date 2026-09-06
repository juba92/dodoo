"""Populate ``ir_model`` rows for HR / Fleet models.

``ir.rule.model_id`` is a FK to ``ir_model``, but nothing in the framework populates that
table today (the 001 access-rule tests insert rows by hand). Each addon calls
:func:`sync_ir_model` from its seed before seeding record rules. Idempotent.
"""

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
