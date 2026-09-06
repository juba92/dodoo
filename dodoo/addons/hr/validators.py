"""Whitelist validation at the HTTP/RPC boundary (FR-065, SEC-001) and group checks (SEC-002/004).

Every REST action body and every custom ``execute_kw`` method's kwargs are parsed through a
Pydantic v2 model with ``extra="forbid"`` — unknown fields are rejected, not silently dropped.
``fleet/validators.py`` re-exports :func:`validate` / :func:`require_groups` from here.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import text

from dodoo.core.exceptions import AccessError, DodooError

_M = TypeVar("_M", bound=BaseModel)


class Payload(BaseModel):
    """Base for every action payload model — forbids unknown fields."""

    model_config = ConfigDict(extra="forbid")


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
        raise DodooError(f"invalid_payload: {errs[0]['loc'][-1]} {errs[0]['msg']}") from exc


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


async def require_groups(env: Any, uid: int | None, *names: str) -> None:
    """Raise ``AccessError`` unless the user is in at least one of ``names``."""
    held = await group_names(env, uid)
    if held.isdisjoint(names):
        raise AccessError(f"requires one of: {', '.join(names)}")
