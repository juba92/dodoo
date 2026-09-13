"""Whitelist validation at the HTTP/RPC boundary (FR-086, SEC-001) and group checks (SEC-002/004).

Every REST action body is parsed through a Pydantic v2 model with ``extra="forbid"`` — unknown
fields are rejected, not silently dropped. This is the canonical copy of these helpers (mirrors
``dodoo/addons/hr/validators.py`` exactly); ``product`` has no dependency to re-export from, so it
hosts them here. ``stock/validators.py`` re-exports from this module (mirrors
``fleet/validators.py`` re-exporting from ``hr``), and ``stock_account/validators.py`` re-exports
from ``stock``.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import text

from dodoo.core.exceptions import AccessError, DodooError

_M = TypeVar("_M", bound=BaseModel)


class Payload(BaseModel):
    """Base for every action payload model — forbids unknown fields."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


def validate(model_cls: type[_M], payload: dict[str, Any] | None) -> _M:
    """Parse ``payload`` into ``model_cls`` or raise ``DodooError`` with a stable code."""
    try:
        return model_cls.model_validate(payload or {})
    except ValidationError as exc:
        errs = exc.errors()
        if any(e.get("type") == "extra_forbidden" for e in errs):
            bad = ", ".join(
                str(e["loc"][-1]) for e in errs if e.get("type") == "extra_forbidden"
            )
            raise DodooError(f"unknown_field: {bad}") from exc
        loc = errs[0].get("loc") or ("",)
        raise DodooError(f"invalid_payload: {loc[-1]} {errs[0]['msg']}") from exc


async def group_names(env: Any, uid: int | None) -> set[str]:
    """Return the set of ``res.groups`` names the user belongs to."""
    if not uid:
        return set()
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text(
                "SELECT g.name FROM res_users_groups_rel r "
                "JOIN res_groups g ON g.id = r.group_id WHERE r.user_id = :uid"
            ),
            {"uid": uid},
        )
        return {row[0] for row in rows}


async def is_member(env: Any, uid: int | None, name: str) -> bool:
    return name in await group_names(env, uid)


def and_domain(*clauses: list) -> list:
    """Combine 2+ domain leaves into the flat, Polish-notation form
    ``dodoo.core.query.compile_domain`` actually requires: ``["&", c1, "&", c2, c3, ...]`` is
    wrong — it must be the FLAT sequence ``["&"] * (n-1) + [c1, c2, ..., cn]`` (each "&" token
    positionally consumes the next two not-yet-consumed expressions as it walks the array).
    A bare list of leaves (Odoo's own "implicit AND") is NOT supported here — every call with
    2+ clauses MUST go through this helper."""
    clauses = list(clauses)
    if len(clauses) <= 1:
        return clauses[0] if clauses else []
    return ["&"] * (len(clauses) - 1) + clauses


async def require_groups(env: Any, uid: int | None, *names: str) -> None:
    """Raise ``AccessError`` unless the user is in at least one of ``names``.

    The ``Administrator`` superuser group always passes.
    """
    held = await group_names(env, uid)
    if "Administrator" in held:
        return
    if held.isdisjoint(names):
        raise AccessError(f"requires one of: {', '.join(names)}")


# --------------------------------------------------------------------------- US1


class AttributeLineSpec(Payload):
    attribute_id: int
    value_ids: list[int]


class ApplyAttributeLines(Payload):
    lines: list[AttributeLineSpec]
