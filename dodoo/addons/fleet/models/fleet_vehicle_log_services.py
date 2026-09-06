"""``fleet.vehicle.log.services`` — a dated service event (FR-057)."""

from __future__ import annotations

from dodoo.core.fields import Char, Date, Many2one, Monetary, Text
from dodoo.core.models import BaseModel


class FleetVehicleLogServices(BaseModel):
    _name = "fleet.vehicle.log.services"

    vehicle_id = Many2one("fleet.vehicle", required=True)
    service_type = Char(size=64, required=True)
    date = Date(required=True)
    amount = Monetary()
    currency_id = Many2one("res.currency")
    notes = Text()
