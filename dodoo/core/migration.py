from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from dodoo.core.exceptions import SchemaConflictError

if TYPE_CHECKING:
    from dodoo.core.models import BaseModel

from dodoo.core.fields import Many2many

_log = logging.getLogger(__name__)

# SA type → PostgreSQL type name mapping for conflict detection
_SA_TO_PG: dict[type, str] = {
    sa.String: "character varying",
    sa.Integer: "integer",
    sa.Boolean: "boolean",
    sa.Float: "double precision",
    sa.Date: "date",
    sa.DateTime: "timestamp without time zone",
    sa.Text: "text",
}


async def _existing_columns(
    conn: sa.ext.asyncio.AsyncConnection, table_name: str
) -> dict[str, str]:
    result = await conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :tbl"
        ),
        {"tbl": table_name},
    )
    return {row[0]: row[1] for row in result}


class MigrationRunner:
    def __init__(self, ddl_engine: AsyncEngine) -> None:
        self._engine = ddl_engine

    async def install(self, model: type[BaseModel]) -> None:
        table_name = model._table_name()
        columns = model._sa_columns()

        async with self._engine.begin() as conn:
            existing = await _existing_columns(conn, table_name)

            if not existing:
                await self._create_table(conn, table_name, columns)
                _log.info("Created table %s", table_name)
            else:
                await self._migrate_table(conn, table_name, columns, existing)

            # Create Many2many junction tables
            for field in model._fields.values():
                if isinstance(field, Many2many) and field.relation_table:
                    col1 = field.column1 or f"{model._table_name()}_id"
                    col2 = field.column2 or f"{field.relation.replace('.', '_')}_id"
                    rel_existing = await _existing_columns(conn, field.relation_table)
                    if not rel_existing:
                        await conn.execute(
                            text(
                                f"CREATE TABLE IF NOT EXISTS {field.relation_table} ("
                                f"  {col1} INTEGER NOT NULL,"
                                f"  {col2} INTEGER NOT NULL,"
                                f"  PRIMARY KEY ({col1}, {col2})"
                                f")"
                            )
                        )
                        _log.info("Created junction table %s", field.relation_table)

    async def _create_table(
        self,
        conn: sa.ext.asyncio.AsyncConnection,
        table_name: str,
        columns: list[sa.Column],  # type: ignore[type-arg]
    ) -> None:
        col_defs = ["id SERIAL PRIMARY KEY"]
        for col in columns:
            nullable = "NOT NULL" if not col.nullable else "NULL"
            col_defs.append(f"{col.name} {col.type.compile(conn.dialect)} {nullable}")
        col_defs += [
            "create_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now()",
            "write_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now()",
        ]
        ddl = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"
        await conn.execute(text(ddl))

    async def _migrate_table(
        self,
        conn: sa.ext.asyncio.AsyncConnection,
        table_name: str,
        columns: list[sa.Column],  # type: ignore[type-arg]
        existing: dict[str, str],
    ) -> None:
        for col in columns:
            if col.name not in existing:
                _log.info("Adding column %s.%s", table_name, col.name)
                ddl = (
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS "
                    f"{col.name} {col.type.compile(conn.dialect)}"
                )
                await conn.execute(text(ddl))
            else:
                # Check for type conflict (destructive change)
                declared_pg = _SA_TO_PG.get(type(col.type), "")
                existing_pg = existing[col.name]
                if declared_pg and declared_pg != existing_pg:
                    raise SchemaConflictError(
                        f"Column '{table_name}.{col.name}': declared type "
                        f"'{declared_pg}' conflicts with existing '{existing_pg}'. "
                        "Destructive migrations are not supported."
                    )

    async def add_discriminator(self, table_name: str) -> None:
        """Add _type discriminator column if not present (for STI parent tables)."""
        async with self._engine.begin() as conn:
            existing = await _existing_columns(conn, table_name)
            if "_type" not in existing:
                await conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS _type VARCHAR(128)")
                )
