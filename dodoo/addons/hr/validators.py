"""Whitelist validation at the HTTP/RPC boundary (FR-065, SEC-001) and group checks (SEC-002/004).

Every REST action body and every custom ``execute_kw`` method's kwargs are parsed through a
Pydantic v2 model with ``extra="forbid"`` — unknown fields are rejected, not silently dropped.
``fleet/validators.py`` re-exports :func:`validate` / :func:`require_groups` from here.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
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


async def require_groups(env: Any, uid: int | None, *names: str) -> None:
    """Raise ``AccessError`` unless the user is in at least one of ``names``."""
    held = await group_names(env, uid)
    if held.isdisjoint(names):
        raise AccessError(f"requires one of: {', '.join(names)}")


# --------------------------------------------------------------------------- P1


class DepartmentCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    company_id: int
    parent_id: int | None = None
    manager_id: int | None = None
    appraisal_frequency_months: int | None = Field(default=None, ge=1, le=60)


class JobCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    company_id: int
    department_id: int | None = None
    expected_employees: int = Field(default=0, ge=0)
    is_published: bool = False


class EmployeeCreate(Payload):
    name: str = Field(min_length=1, max_length=256)
    company_id: int
    work_email: str | None = Field(default=None, max_length=256)
    work_phone: str | None = Field(default=None, max_length=64)
    department_id: int | None = None
    job_id: int | None = None
    job_title: str | None = Field(default=None, max_length=128)
    work_location: str | None = Field(default=None, max_length=128)
    manager_id: int | None = None
    coach_id: int | None = None
    user_id: int | None = None
    category_ids: list[int] = Field(default_factory=list)
    gender: Literal["male", "female", "other"] | None = None
    birthday: _dt.date | None = None
    marital: (
        Literal["single", "married", "cohabitant", "widower", "divorced"] | None
    ) = None
    private_email: str | None = Field(default=None, max_length=256)
    private_phone: str | None = Field(default=None, max_length=64)
    emergency_contact: str | None = Field(default=None, max_length=128)
    emergency_phone: str | None = Field(default=None, max_length=64)
    country_id: int | None = None
    identification_id: str | None = Field(default=None, max_length=64)
    bank_account: str | None = Field(default=None, max_length=64)
    home_address: str | None = None
    dependant_count: int = Field(default=0, ge=0)


class ContractCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    employee_id: int
    company_id: int
    contract_type_id: int | None = None
    currency_id: int | None = None
    wage: float = Field(default=0, ge=0)
    date_start: _dt.date
    date_end: _dt.date | None = None
    trial_date_end: _dt.date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self) -> ContractCreate:
        if self.date_end and self.date_end < self.date_start:
            raise ValueError("date_end before date_start")
        if self.trial_date_end:
            if self.trial_date_end < self.date_start:
                raise ValueError("trial before start")
            if self.date_end and self.trial_date_end > self.date_end:
                raise ValueError("trial after end")
        return self


class ContractSetState(Payload):
    state: Literal["draft", "running", "expired", "cancelled"]
    expected_state: Literal["draft", "running", "expired", "cancelled"] | None = None


class EmployeeSkillCreate(Payload):
    employee_id: int
    skill_id: int
    skill_level_id: int
