from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa

from dodoo.core.exceptions import DomainError

_SYSTEM_COLS = frozenset({"id", "create_date", "write_date", "_type"})
_VALID_OPS = frozenset({"=", "!=", "<", ">", "<=", ">=", "in", "not in", "like", "ilike"})

# Resolver: model name -> (its SA table, its {field_name: Field} map incl. system cols).
Resolver = Callable[[str], "tuple[sa.Table, dict[str, Any]]"]


def compile_domain(
    table: sa.Table,
    fields: dict[str, Any],
    domain: list,
    *,
    context: dict[str, Any] | None = None,
    resolve: Resolver | None = None,
) -> sa.ClauseElement:
    """Compile an Odoo-style domain list to a SQLAlchemy WHERE clause.

    ``context`` (optional) resolves ``$``-prefixed placeholder leaf values —
    ``$uid`` / ``$company_id`` / ``$company_ids`` / ``$today`` — from
    :meth:`dodoo.auth.access.AccessEnforcer.build_context` output. ``resolve`` (optional)
    enables dotted-path leaves (``employee_id.user_id``) by returning the related model's
    table + field map; each hop compiles to ``head_fk IN (SELECT id FROM rel WHERE …)``.
    Both default to off, so existing callers are unaffected.
    """
    if not domain:
        return sa.true()
    return _parse(table, fields, domain, 0, context, resolve)[0]


def _resolve_token(value: Any, context: dict[str, Any] | None) -> Any:
    if not (isinstance(value, str) and value.startswith("$")):
        return value
    if value == "$today":
        return datetime.date.today()
    ctx = context or {}
    key = value[1:]
    if key not in ctx:
        raise DomainError(f"Unknown domain placeholder {value!r}")
    return ctx[key]


def _parse(
    table: sa.Table,
    fields: dict[str, Any],
    domain: list,
    pos: int,
    context: dict[str, Any] | None,
    resolve: Resolver | None,
) -> tuple[sa.ClauseElement, int]:
    item = domain[pos]

    if item == "&":
        left, pos = _parse(table, fields, domain, pos + 1, context, resolve)
        right, pos = _parse(table, fields, domain, pos, context, resolve)
        return sa.and_(left, right), pos
    if item == "|":
        left, pos = _parse(table, fields, domain, pos + 1, context, resolve)
        right, pos = _parse(table, fields, domain, pos, context, resolve)
        return sa.or_(left, right), pos
    if item == "!":
        expr, pos = _parse(table, fields, domain, pos + 1, context, resolve)
        return sa.not_(expr), pos

    if not (isinstance(item, list | tuple) and len(item) == 3):
        raise DomainError(f"Invalid domain leaf: {item!r}")

    field_name, op_str, value = item
    return _leaf(table, fields, field_name, op_str, value, context, resolve), pos + 1


def _leaf(
    table: sa.Table,
    fields: dict[str, Any],
    field_name: str,
    op_str: str,
    value: Any,
    context: dict[str, Any] | None,
    resolve: Resolver | None,
) -> sa.ClauseElement:
    if op_str not in _VALID_OPS:
        raise DomainError(f"Unsupported operator '{op_str}'")

    # Placeholder substitution ($uid, $company_ids, ...).
    if isinstance(value, list):
        value = [_resolve_token(v, context) for v in value]
    else:
        value = _resolve_token(value, context)

    # Dotted path: employee_id.user_id -> correlated subquery on the related table.
    if "." in field_name:
        head, _, rest = field_name.partition(".")
        field = fields.get(head)
        relation = getattr(field, "relation", None)
        if relation is None:
            raise DomainError(
                f"Relational domain leaf '{field_name}' requires a Many2one head field"
            )
        if resolve is None:
            raise DomainError(
                f"Relational domain leaf '{field_name}' needs a resolver (no context)"
            )
        rel_table, rel_fields = resolve(relation)
        sub_clause = _leaf(rel_table, rel_fields, rest, op_str, value, context, resolve)
        return table.c[head].in_(sa.select(rel_table.c.id).where(sub_clause))

    if field_name not in fields and field_name not in _SYSTEM_COLS:
        raise DomainError(f"Unknown field '{field_name}' in domain")

    col = table.c[field_name]

    if value is None and op_str == "=":
        return col.is_(None)
    if value is None and op_str == "!=":
        return col.isnot(None)

    if op_str == "=":
        return col == value
    if op_str == "!=":
        return col != value
    if op_str == "<":
        return col < value
    if op_str == ">":
        return col > value
    if op_str == "<=":
        return col <= value
    if op_str == ">=":
        return col >= value
    if op_str == "in":
        return col.in_(value)
    if op_str == "not in":
        return col.notin_(value)
    if op_str == "like":
        return col.like(value)
    if op_str == "ilike":
        return col.ilike(value)
    raise DomainError(f"Unsupported operator '{op_str}'")  # pragma: no cover
