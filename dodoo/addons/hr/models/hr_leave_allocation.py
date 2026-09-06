"""``hr.leave.allocation`` — entitlement grant, regular or accrual (FR-022, FR-023, ADR-025)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Date, Float, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

MODE = [("regular", "Regular"), ("accrual", "Accrual")]
ACCRUAL_PERIOD = [("day", "Day"), ("week", "Week"), ("month", "Month")]
STATE = [("draft", "Draft"), ("confirmed", "Confirmed"), ("refused", "Refused")]

_PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}


class HrLeaveAllocation(BaseModel):
    _name = "hr.leave.allocation"

    employee_id = Many2one("hr.employee", required=True)
    leave_type_id = Many2one("hr.leave.type", required=True)
    company_id = Many2one("res.company", required=True)
    mode = Selection(MODE, default="regular")
    number_of_units = Float(default=0.0)
    accrual_rate = Float(default=0.0)
    accrual_period = Selection(ACCRUAL_PERIOD)
    accrual_max = Float()
    date_from = Date()
    date_to = Date()
    last_accrual_date = Date()
    state = Selection(STATE, default="confirmed")

    @staticmethod
    def _check_accrual(vals: dict[str, Any]) -> None:
        if vals.get("mode") == "accrual":
            if not vals.get("accrual_rate") or not vals.get("accrual_period"):
                raise DodooError("accrual_config_invalid")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        cls._check_accrual(vals)
        if vals.get("mode") == "accrual" and not vals.get("last_accrual_date"):
            vals = {
                **vals,
                "last_accrual_date": vals.get("date_from") or datetime.date.today(),
            }
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if "mode" in vals or "accrual_rate" in vals or "accrual_period" in vals:
            for aid in ids:
                cur = await super().read(
                    env, [aid], ["mode", "accrual_rate", "accrual_period"]
                )
                merged = {**(cur[0] if cur else {}), **vals}
                cls._check_accrual(merged)
        return await super().write(env, ids, vals)

    @classmethod
    async def run_leave_accrual(cls, env: Environment) -> dict[str, Any]:
        """Idempotently add ``floor(periods elapsed) * rate`` capped at ``accrual_max``."""
        today = datetime.date.today()
        updated = 0
        units_added = 0.0
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, number_of_units, accrual_rate, accrual_period, "
                    "       accrual_max, last_accrual_date "
                    "FROM hr_leave_allocation "
                    "WHERE mode = 'accrual' AND state = 'confirmed'"
                )
            )
            allocs = [dict(r._mapping) for r in rows]

            for a in allocs:
                last = a["last_accrual_date"]
                if isinstance(last, str):
                    last = datetime.date.fromisoformat(last[:10])
                if last is None:
                    last = today
                period_days = _PERIOD_DAYS[a["accrual_period"]]
                elapsed = (today - last).days
                periods = elapsed // period_days
                if periods <= 0:
                    continue
                units_now = float(a["number_of_units"] or 0)
                add = periods * float(a["accrual_rate"] or 0)
                new_total = units_now + add
                cap = a["accrual_max"]
                if cap:
                    new_total = min(new_total, float(cap))
                    add = new_total - units_now
                if add <= 0:
                    await conn.execute(
                        text(
                            "UPDATE hr_leave_allocation SET last_accrual_date = :d, "
                            "write_date = now() WHERE id = :i"
                        ),
                        {"d": last + datetime.timedelta(days=periods * period_days), "i": a["id"]},
                    )
                    continue
                await conn.execute(
                    text(
                        "UPDATE hr_leave_allocation SET number_of_units = :n, "
                        "last_accrual_date = :d, write_date = now() WHERE id = :i"
                    ),
                    {
                        "n": new_total,
                        "d": last + datetime.timedelta(days=periods * period_days),
                        "i": a["id"],
                    },
                )
                updated += 1
                units_added += add
            await conn.commit()

        _log.info(
            "hr.transition model=hr.leave.allocation event=leave_accrual updated=%s units_added=%s",
            updated,
            units_added,
        )
        return {"updated": updated, "units_added": round(units_added, 4)}
