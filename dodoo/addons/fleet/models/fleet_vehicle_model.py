"""``fleet.vehicle.model.brand`` + ``fleet.vehicle.model`` — the vehicle catalog (FR-052).

Both are global (no ``company_id``).
"""

from __future__ import annotations

from dodoo.core.fields import Char, Many2one
from dodoo.core.models import BaseModel


class FleetVehicleModelBrand(BaseModel):
    _name = "fleet.vehicle.model.brand"

    name = Char(size=64, required=True)


class FleetVehicleModel(BaseModel):
    _name = "fleet.vehicle.model"

    name = Char(size=64, required=True)
    brand_id = Many2one("fleet.vehicle.model.brand", required=True)
