"""Whitelist validation payloads for analytic accounting (contracts/reports-analytic.md).

``analytic`` has no group of its own (plan.md D8) — gating for mutating analytic actions is
done by whichever depending addon calls into these models (``account``'s "Accounting Manager").
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from dodoo.core.exceptions import DodooError

_M = TypeVar("_M", bound=BaseModel)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


def validate(model_cls: type[_M], payload: dict[str, Any] | None) -> _M:
    try:
        return model_cls.model_validate(payload or {})
    except ValidationError as exc:
        errs = exc.errors()
        if any(e.get("type") == "extra_forbidden" for e in errs):
            bad = ", ".join(str(e["loc"][-1]) for e in errs if e.get("type") == "extra_forbidden")
            raise DodooError(f"unknown_field: {bad}") from exc
        loc = errs[0].get("loc") or ("",)
        raise DodooError(f"invalid_payload: {loc[-1]} {errs[0]['msg']}") from exc


class AnalyticPlanCreate(Payload):
    name: str
    parent_id: int | None = None
    company_id: int


class AnalyticAccountCreate(Payload):
    name: str
    code: str | None = None
    plan_id: int | None = None
    company_id: int
    active: bool = True
