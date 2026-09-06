"""``fleet.vehicle.odometer`` — a dated mileage reading (FR-055, ADR-027).

A value below the vehicle's current max is accepted but flagged ``inconsistent`` and logged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.fields import Boolean, Date, Float, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class FleetVehicleOdometer(BaseModel):
    _name = "fleet.vehicle.odometer"

    vehicle_id = Many2one("fleet.vehicle", required=True)
    value = Float(required=True)
    date = Date(required=True)
    inconsistent = Boolean(default=False)

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        vals = dict(vals)
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT MAX(value) FROM fleet_vehicle_odometer WHERE vehicle_id = :v"
                ),
                {"v": vals["vehicle_id"]},
            )
            current_max = row.scalar_one_or_none()
        if current_max is not None and float(vals["value"]) < float(current_max):
            vals["inconsistent"] = True
            _log.warning(
                "hr.transition model=fleet.vehicle.odometer event=odometer_inconsistent "
                "vehicle_id=%s value=%s prev_max=%s",
                vals["vehicle_id"],
                vals["value"],
                current_max,
            )
        return await super().create(env, vals)

    @classmethod
    async def latest_for(cls, env: Environment, vehicle_id: int) -> dict[str, Any] | None:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT id, value, date FROM fleet_vehicle_odometer "
                    "WHERE vehicle_id = :v ORDER BY date DESC, id DESC LIMIT 1"
                ),
                {"v": vehicle_id},
            )
            r = row.fetchone()
        return dict(r._mapping) if r else None
