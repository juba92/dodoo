"""Re-exports the canonical whitelist-validation helpers from `product` (stock depends on
product, mirrors `fleet/validators.py` re-exporting from `hr`), plus every stock-specific
Payload subclass."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from dodoo.addons.product.validators import (  # noqa: F401
    Payload,
    and_domain,
    group_names,
    is_member,
    require_groups,
    validate,
)

# --------------------------------------------------------------------------- US2


class WarehouseCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=16)
    company_id: int
    address: str | None = None
    reception_steps: Literal["one_step", "two_steps", "three_steps"] = "one_step"
    delivery_steps: Literal["one_step", "two_steps", "three_steps"] = "one_step"


class WarehouseStepsUpdate(Payload):
    reception_steps: Literal["one_step", "two_steps", "three_steps"] | None = None
    delivery_steps: Literal["one_step", "two_steps", "three_steps"] | None = None


class LocationCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None
    usage: Literal[
        "internal", "customer", "vendor", "inventory", "production", "transit", "view"
    ]
    warehouse_id: int | None = None


class PickingTypeCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    code: Literal["incoming", "outgoing", "internal"]
    warehouse_id: int
    default_location_src_id: int | None = None
    default_location_dest_id: int | None = None
    reservation_mode: Literal["immediate", "manual"] = "immediate"
    backorder_policy: Literal["ask", "always", "never"] = "ask"


# --------------------------------------------------------------------------- US3


class MoveSpec(Payload):
    product_id: int
    product_uom_qty: float = Field(gt=0)
    product_uom_id: int
    location_src_id: int | None = None
    location_dest_id: int | None = None


class TransferCreate(Payload):
    picking_type_id: int
    partner_id: int | None = None
    scheduled_date: datetime | None = None
    moves: list[MoveSpec]


class TransferValidate(Payload):
    expected_state: Literal["draft", "waiting", "confirmed", "ready"]
    create_backorder: bool | None = None


class TransferCancel(Payload):
    expected_state: Literal["draft", "waiting", "confirmed", "ready"]


class MoveLineUpdate(Payload):
    qty_done: float = Field(ge=0)
    lot_id: int | None = None
    package_id: int | None = None
    result_package_id: int | None = None


# --------------------------------------------------------------------------- US4


class CountLine(Payload):
    quant_id: int
    counted_quantity: float = Field(ge=0)


class CountSet(Payload):
    lines: list[CountLine]


class CountApply(Payload):
    quant_ids: list[int]


# --------------------------------------------------------------------------- US5


class LotCreate(Payload):
    name: str = Field(min_length=1, max_length=64)
    product_id: int
    company_id: int
    expiration_date: date | None = None


class PackageMove(Payload):
    location_dest_id: int


class TrackingUpdate(Payload):
    tracking: Literal["none", "lot", "serial"]


# --------------------------------------------------------------------------- US6


class StorageCategoryCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    max_weight: float | None = None
    max_packages: int | None = None
    allow_new_product: Literal["always", "same_product", "same_lot"] = "always"
    location_ids: list[int] = []


class PutawayRuleCreate(Payload):
    location_src_id: int
    product_id: int | None = None
    category_id: int | None = None
    location_dest_id: int
    sequence: int = 10

    @model_validator(mode="after")
    def _one_of_product_or_category(self) -> "PutawayRuleCreate":
        if bool(self.product_id) == bool(self.category_id):
            raise ValueError("exactly one of product_id or category_id is required")
        return self


class OrderpointCreate(Payload):
    product_id: int
    location_id: int
    product_min_qty: float = Field(ge=0)
    product_max_qty: float = Field(ge=0)
    qty_multiple: float = Field(gt=0, default=1.0)


class RunReordering(Payload):
    orderpoint_ids: list[int] | None = None


# --------------------------------------------------------------------------- US7


class ScrapCreate(Payload):
    product_id: int
    lot_id: int | None = None
    quantity: float = Field(gt=0)
    location_src_id: int
    location_dest_id: int
    reason: str | None = Field(default=None, max_length=256)
