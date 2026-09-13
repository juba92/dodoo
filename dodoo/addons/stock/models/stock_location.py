"""``stock.location`` — a node in the hierarchical storage tree (FR-015/016)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

USAGE_CHOICES = [
    ("internal", "Internal"),
    ("customer", "Customer"),
    ("vendor", "Vendor"),
    ("inventory", "Inventory Loss"),
    ("production", "Production"),
    ("transit", "Transit"),
    ("view", "View"),
]


class StockLocation(BaseModel):
    _name = "stock.location"

    name = Char(size=128, required=True)
    parent_id = Many2one("stock.location")
    usage = Selection(USAGE_CHOICES, required=True, default="internal")
    warehouse_id = Many2one("stock.warehouse")
    company_id = Many2one("res.company")
    active = Boolean(default=True)
    scrap_location = Boolean(default=False)

    @classmethod
    async def _assert_no_cycle(
        cls, env: Environment, location_id: int, parent_id: int | None
    ) -> None:
        seen = {location_id}
        current = parent_id
        while current is not None:
            if current in seen:
                raise DodooError("location_cycle")
            seen.add(current)
            rows = await super(StockLocation, cls).read(env, [current], ["parent_id"])
            current = rows[0]["parent_id"] if rows else None

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if "parent_id" in vals and vals["parent_id"] is not None:
            for lid in ids:
                await cls._assert_no_cycle(env, lid, vals["parent_id"])
        return await super().write(env, ids, vals)

    @classmethod
    def counts_as_company_stock(cls, usage: str) -> bool:
        """Only `internal` locations count toward on-hand totals (FR-016)."""
        return usage == "internal"
