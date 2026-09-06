"""``hr.public.holiday`` — non-working date range, global or per company (FR-021)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Date, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class HrPublicHoliday(BaseModel):
    _name = "hr.public.holiday"

    name = Char(size=64, required=True)
    date_from = Date(required=True)
    date_to = Date(required=True)
    company_id = Many2one("res.company")  # nullable → global

    @staticmethod
    def _check(vals: dict[str, Any], current: dict[str, Any] | None = None) -> None:
        base = dict(current or {})
        base.update({k: v for k, v in vals.items() if v is not None})
        df, dt = base.get("date_from"), base.get("date_to")
        if df and dt and str(dt) < str(df):
            raise DodooError("public_holiday_dates")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        cls._check(vals)
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if {"date_from", "date_to"} & set(vals):
            for hid in ids:
                cur = await super().read(env, [hid], ["date_from", "date_to"])
                cls._check(vals, cur[0] if cur else None)
        return await super().write(env, ids, vals)
