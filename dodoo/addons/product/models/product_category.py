"""``product.category`` — hierarchical product grouping (FR-001).

Carries no costing/accounting fields: ``costing_method`` and the three stock-valuation account
properties are added to this table by ``stock_account`` via ``ALTER TABLE`` (D1/ADR-033), never
declared here, so this model stays free of any dependency on `stock`/`account`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class ProductCategory(BaseModel):
    _name = "product.category"

    name = Char(size=128, required=True)
    parent_id = Many2one("product.category")
    company_id = Many2one("res.company")

    @classmethod
    async def _assert_no_cycle(
        cls, env: Environment, category_id: int, parent_id: int | None
    ) -> None:
        seen = {category_id}
        current = parent_id
        while current is not None:
            if current in seen:
                raise DodooError("category_cycle")
            seen.add(current)
            rows = await super(ProductCategory, cls).read(env, [current], ["parent_id"])
            current = rows[0]["parent_id"] if rows else None

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if "parent_id" in vals and vals["parent_id"] is not None:
            for cid in ids:
                await cls._assert_no_cycle(env, cid, vals["parent_id"])
        return await super().write(env, ids, vals)
