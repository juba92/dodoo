from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from dodoo.core.exceptions import DomainError

_SYSTEM_COLS = frozenset({"id", "create_date", "write_date", "_type"})
_VALID_OPS = frozenset({"=", "!=", "<", ">", "<=", ">=", "in", "not in", "like", "ilike"})


def compile_domain(
    table: sa.Table,
    fields: dict[str, Any],
    domain: list,
) -> sa.ClauseElement:
    if not domain:
        return sa.true()
    return _parse(table, fields, domain, 0)[0]


def _parse(
    table: sa.Table,
    fields: dict[str, Any],
    domain: list,
    pos: int,
) -> tuple[sa.ClauseElement, int]:
    item = domain[pos]

    if item == "&":
        left, pos = _parse(table, fields, domain, pos + 1)
        right, pos = _parse(table, fields, domain, pos)
        return sa.and_(left, right), pos
    if item == "|":
        left, pos = _parse(table, fields, domain, pos + 1)
        right, pos = _parse(table, fields, domain, pos)
        return sa.or_(left, right), pos
    if item == "!":
        expr, pos = _parse(table, fields, domain, pos + 1)
        return sa.not_(expr), pos

    if not (isinstance(item, list | tuple) and len(item) == 3):
        raise DomainError(f"Invalid domain leaf: {item!r}")

    field_name, op_str, value = item

    if field_name not in fields and field_name not in _SYSTEM_COLS:
        raise DomainError(f"Unknown field '{field_name}' in domain")

    if op_str not in _VALID_OPS:
        raise DomainError(f"Unsupported operator '{op_str}'")

    col = table.c[field_name]

    if op_str == "=":
        clause: sa.ClauseElement = col == value
    elif op_str == "!=":
        clause = col != value
    elif op_str == "<":
        clause = col < value
    elif op_str == ">":
        clause = col > value
    elif op_str == "<=":
        clause = col <= value
    elif op_str == ">=":
        clause = col >= value
    elif op_str == "in":
        clause = col.in_(value)
    elif op_str == "not in":
        clause = col.notin_(value)
    elif op_str == "like":
        clause = col.like(value)
    elif op_str == "ilike":
        clause = col.ilike(value)
    else:
        raise DomainError(f"Unsupported operator '{op_str}'")

    return clause, pos + 1
