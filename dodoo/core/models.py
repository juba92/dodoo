from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import _RESERVED, Field, Many2many, One2many
from dodoo.core.query import compile_domain

if TYPE_CHECKING:
    from dodoo import Environment

_SYSTEM_FIELDS = ("id", "create_date", "write_date")

# Global set of all model classes created by _ModelMeta (used by installer)
_ALL_MODELS: list[type] = []


def _humanize(field_name: str) -> str:
    """Odoo-style fallback label for a field with no explicit ``string=``.

    ``invoice_date_due`` → ``Invoice Date Due``; a trailing ``_id`` / ``_ids`` is
    dropped so relational fields read as ``Partner``, not ``Partner Id``.
    """
    name = field_name
    for suffix in ("_ids", "_id"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", " ").strip().title()


def _translate_label(text: str) -> str:
    """Run a field label through the localization catalog for the active request language.

    Inert (identity) when the ``localization`` addon is not installed — its ``i18n`` module
    is imported lazily so ``core`` keeps no dependency on the addon.
    """
    try:
        from dodoo.addons.localization.i18n import translate
        from dodoo.core.context import get_lang

        return translate(text, get_lang())
    except Exception:
        return text


class _ModelMeta(type):
    def __new__(
        mcs,  # noqa: N804
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        cls = super().__new__(mcs, name, bases, namespace)

        if name == "BaseModel":
            return cls

        # Collect Field instances from class attrs
        fields: dict[str, Field] = {}
        for attr_name, val in list(namespace.items()):
            if isinstance(val, Field):
                if attr_name in _RESERVED:
                    raise DodooError(
                        f"Field name '{attr_name}' is reserved and cannot be used in model '{name}'"
                    )
                val.name = attr_name
                fields[attr_name] = val

        cls._fields = fields  # type: ignore[attr-defined]

        # Auto-set _name if not declared
        if not getattr(cls, "_name", None):
            cls._name = name.lower()  # type: ignore[attr-defined]

        _ALL_MODELS.append(cls)
        return cls


class BaseModel(metaclass=_ModelMeta):
    _name: str = ""
    _inherit: str = ""
    _abstract: bool = False  # True → no DB table; skip migration
    _fields: dict[str, Field] = {}

    @classmethod
    def _table_name(cls) -> str:
        return cls._name.replace(".", "_")

    @classmethod
    def _sa_table(cls) -> sa.Table:
        meta = sa.MetaData()
        cols: list[sa.Column] = [  # type: ignore[type-arg]
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        ]
        for field in cls._fields.values():
            col = field.to_sa_column()
            if col is not None:
                cols.append(col)
        cols += [
            sa.Column("create_date", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("write_date", sa.DateTime(), server_default=sa.func.now()),
        ]
        if cls._inherit:
            cols.append(sa.Column("_type", sa.String(128)))
        return sa.Table(cls._table_name(), meta, *cols)

    @classmethod
    def _sa_columns(cls) -> list[sa.Column]:  # type: ignore[type-arg]
        cols = []
        for field in cls._fields.values():
            col = field.to_sa_column()
            if col is not None:
                cols.append(col)
        return cols

    @classmethod
    def _all_field_names(cls) -> list[str]:
        names = list(_SYSTEM_FIELDS)
        names += [
            n
            for n in cls._fields
            if not isinstance(cls._fields[n], One2many | Many2many)
        ]
        return names

    # ---- Many2many helpers ----

    @classmethod
    def _m2m_fields(cls) -> dict[str, Many2many]:
        """Writable Many2many fields (those backed by a junction table)."""
        return {
            n: f
            for n, f in cls._fields.items()
            if isinstance(f, Many2many) and f.relation_table
        }

    @classmethod
    def _m2m_columns(cls, field: Many2many) -> tuple[str, str]:
        """(source_column, target_column) of a Many2many junction table.

        Mirrors ``MigrationRunner`` so declared column names win and the
        defaults match the tables it creates.
        """
        col1 = field.column1 or f"{cls._table_name()}_id"
        col2 = field.column2 or f"{field.relation.replace('.', '_')}_id"
        return col1, col2

    @staticmethod
    def _m2m_id_list(value: Any) -> list[int]:
        """Normalise a Many2many write value to a de-duplicated list of ids.

        Accepts ``None`` / ``False`` (clear) or an iterable of ints. The full
        Odoo command protocol ``(6, 0, ids)`` is intentionally not supported —
        a plain id list is the only form the SPA sends.
        """
        if not value:
            return []
        seen: dict[int, None] = {}
        for item in value:
            seen.setdefault(int(item), None)
        return list(seen)

    @classmethod
    async def _write_m2m(
        cls, conn: Any, field: Many2many, source_id: int, target_ids: list[int]
    ) -> None:
        col1, col2 = cls._m2m_columns(field)
        await conn.execute(
            text(f"DELETE FROM {field.relation_table} WHERE {col1} = :sid"),
            {"sid": source_id},
        )
        for tid in target_ids:
            await conn.execute(
                text(
                    f"INSERT INTO {field.relation_table} ({col1}, {col2}) "
                    f"VALUES (:sid, :tid) ON CONFLICT DO NOTHING"
                ),
                {"sid": source_id, "tid": tid},
            )

    # ---- CRUD ----

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        table = cls._sa_table()
        m2m = cls._m2m_fields()
        m2m_vals = {k: cls._m2m_id_list(vals[k]) for k in m2m if k in vals}
        async with env.dml_conn() as conn:
            row = {
                k: cls._fields[k].coerce(v)
                for k, v in vals.items()
                if k in cls._fields and k not in m2m
            }
            if cls._inherit:
                row["_type"] = cls._name
            result = await conn.execute(
                table.insert().values(**row).returning(table.c.id)
            )
            new_id = result.scalar_one()
            for k, target_ids in m2m_vals.items():
                await cls._write_m2m(conn, m2m[k], new_id, target_ids)
            await conn.commit()
            return new_id

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        table = cls._sa_table()
        allowed = set(cls._all_field_names())
        col_names = [f for f in (fields or cls._all_field_names()) if f in allowed]
        if "id" not in col_names:
            col_names = ["id", *col_names]
        cols = [table.c[f] for f in col_names]

        # Many2many fields are virtual — only returned when explicitly requested.
        m2m = cls._m2m_fields()
        req_m2m = [f for f in (fields or ()) if f in m2m]

        query = sa.select(*cols).where(table.c.id.in_(ids))
        if cls._inherit:
            query = query.where(table.c._type == cls._name)

        async with env.dml_conn() as conn:
            result = await conn.execute(query)
            records = [dict(r) for r in result.mappings().all()]

            for fname in req_m2m:
                field = m2m[fname]
                col1, col2 = cls._m2m_columns(field)
                rel_rows = await conn.execute(
                    text(
                        f"SELECT {col1} AS sid, {col2} AS tid "
                        f"FROM {field.relation_table} WHERE {col1} = ANY(:ids)"
                    ),
                    {"ids": ids},
                )
                by_source: dict[int, list[int]] = {}
                for r in rel_rows:
                    by_source.setdefault(r.sid, []).append(r.tid)
                for rec in records:
                    rec[fname] = by_source.get(rec["id"], [])

        return records

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        table = cls._sa_table()
        m2m = cls._m2m_fields()
        m2m_vals = {k: cls._m2m_id_list(vals[k]) for k in m2m if k in vals}
        row = {
            k: cls._fields[k].coerce(v)
            for k, v in vals.items()
            if k in cls._fields and k not in m2m
        }
        row["write_date"] = sa.func.now()
        query = sa.update(table).where(table.c.id.in_(ids)).values(**row)
        if cls._inherit:
            query = query.where(table.c._type == cls._name)
        async with env.dml_conn() as conn:
            await conn.execute(query)
            for k, target_ids in m2m_vals.items():
                for source_id in ids:
                    await cls._write_m2m(conn, m2m[k], source_id, target_ids)
            await conn.commit()
        return True

    @classmethod
    async def unlink(cls, env: Environment, ids: list[int]) -> bool:
        table = cls._sa_table()
        query = sa.delete(table).where(table.c.id.in_(ids))
        if cls._inherit:
            query = query.where(table.c._type == cls._name)
        async with env.dml_conn() as conn:
            await conn.execute(query)
            await conn.commit()
        return True

    @classmethod
    async def search(
        cls,
        env: Environment,
        domain: list | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
        uid: int | None = None,
    ) -> list[int]:
        table = cls._sa_table()
        where = compile_domain(
            table, {**cls._fields, **{f: None for f in _SYSTEM_FIELDS}}, domain or []
        )

        if cls._inherit:
            where = sa.and_(where, table.c._type == cls._name)

        # Access rule injection (if uid provided)
        if uid is not None:
            rule_domain = await _get_access_domain(env, cls._name, uid, "read")
            if rule_domain:
                rule_clause = compile_domain(
                    table,
                    {**cls._fields, **{f: None for f in _SYSTEM_FIELDS}},
                    rule_domain,
                )
                where = sa.and_(where, rule_clause)

        query = sa.select(table.c.id).where(where)
        if order:
            query = query.order_by(text(order))
        if limit is not None:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        async with env.dml_conn() as conn:
            result = await conn.execute(query)
            return [row[0] for row in result]

    @classmethod
    async def search_read(
        cls,
        env: Environment,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
        uid: int | None = None,
    ) -> list[dict[str, Any]]:
        ids = await cls.search(env, domain, limit, offset, order, uid=uid)
        if not ids:
            return []
        return await cls.read(env, ids, fields)

    @classmethod
    async def fields_get(
        cls, env: Environment, attributes: list[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        result = {}
        for fname, field in cls._fields.items():
            info: dict[str, Any] = {
                "type": type(field).__name__.lower(),
                "string": _translate_label(field.string or _humanize(fname)),
                "required": field.required,
                "readonly": field.readonly,
            }
            if attributes:
                info = {k: v for k, v in info.items() if k in attributes}
            result[fname] = info
        return result


async def _get_access_domain(
    env: Environment, model_name: str, uid: int, operation: str
) -> list | None:
    """Return merged access domain from ir.rule for (model, uid, operation), or None."""
    try:
        from dodoo.auth.access import AccessEnforcer

        return await AccessEnforcer.get_merged_domain(env, model_name, uid, operation)
    except Exception:
        return None
