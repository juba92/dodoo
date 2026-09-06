"""Fleet HTTP-boundary whitelist validators (re-uses the ``hr`` helpers)."""

from __future__ import annotations

import datetime as _dt
from typing import Literal

from pydantic import Field, model_validator

from dodoo.addons.hr.validators import (  # noqa: F401
    Payload,
    group_names,
    is_member,
    require_groups,
    validate,
)

_STATES = (
    "new_request",
    "to_order",
    "ordered",
    "registered",
    "downgraded",
    "reserved",
    "waiting_list",
)


class BrandCreate(Payload):
    name: str = Field(min_length=1, max_length=64)


class ModelCreate(Payload):
    name: str = Field(min_length=1, max_length=64)
    brand_id: int


class VehicleCreate(Payload):
    model_id: int
    license_plate: str | None = Field(default=None, max_length=32)
    company_id: int
    state: Literal[
        "new_request", "to_order", "ordered", "registered",
        "downgraded", "reserved", "waiting_list",
    ] = "new_request"
    driver_id: int | None = None


class VehicleSetState(Payload):
    state: Literal[
        "new_request", "to_order", "ordered", "registered",
        "downgraded", "reserved", "waiting_list",
    ]
    expected_state: Literal[
        "new_request", "to_order", "ordered", "registered",
        "downgraded", "reserved", "waiting_list",
    ] | None = None


class AssignDriver(Payload):
    driver_id: int | None = None


class OdometerCreate(Payload):
    vehicle_id: int
    value: float = Field(ge=0)
    date: _dt.date


class ContractLogCreate(Payload):
    vehicle_id: int
    cost_type: Literal["leasing", "insurance"]
    amount: float = Field(default=0, ge=0)
    start_date: _dt.date
    expiration_date: _dt.date

    @model_validator(mode="after")
    def _order(self) -> ContractLogCreate:
        if self.expiration_date < self.start_date:
            raise ValueError("expiration_date before start_date")
        return self


class ServiceLogCreate(Payload):
    vehicle_id: int
    service_type: str = Field(min_length=1, max_length=64)
    date: _dt.date
    amount: float = Field(default=0, ge=0)
    notes: str | None = None
