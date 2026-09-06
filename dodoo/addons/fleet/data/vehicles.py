"""Fleet area — models, indexes, ir.rule rows, and sample brands/models."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from dodoo.addons.fleet.data import rules, seed

_log = logging.getLogger(__name__)

_MODELS = [
    ("fleet.vehicle.model.brand", "fleet_vehicle_model_brand"),
    ("fleet.vehicle.model", "fleet_vehicle_model"),
    ("fleet.vehicle", "fleet_vehicle"),
    ("fleet.vehicle.odometer", "fleet_vehicle_odometer"),
    ("fleet.vehicle.log.contract", "fleet_vehicle_log_contract"),
    ("fleet.vehicle.log.services", "fleet_vehicle_log_services"),
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_fleet_vehicle_company ON fleet_vehicle (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_fleet_vehicle_driver ON fleet_vehicle (driver_id)",
    "CREATE INDEX IF NOT EXISTS idx_fleet_vehicle_state ON fleet_vehicle (state)",
    "CREATE INDEX IF NOT EXISTS idx_fleet_odometer_vehicle_date "
    "ON fleet_vehicle_odometer (vehicle_id, date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fleet_log_contract_expiry "
    "ON fleet_vehicle_log_contract (expiration_date)",
    "CREATE INDEX IF NOT EXISTS idx_fleet_log_contract_vehicle "
    "ON fleet_vehicle_log_contract (vehicle_id)",
    "CREATE INDEX IF NOT EXISTS idx_fleet_log_services_vehicle "
    "ON fleet_vehicle_log_services (vehicle_id)",
]

# `manager_full` / `officer_read` filter on `company_id`; only `fleet.vehicle` has that
# column, so the odometer / contract / service logs get permissive Fleet-Manager rules
# (they hang off a vehicle the manager already controls).
_RULES = [
    rules.manager_full("fleet.vehicle"),
    rules.officer_read("fleet.vehicle"),
    {
        "name": "fleet.vehicle: driver reads own",
        "model": "fleet.vehicle",
        "domain": [["driver_id.user_id", "=", "$uid"]],
        "groups": ["HR Employee"],
        "perms": "r",
    },
    rules.deny_all("fleet.vehicle"),
    *[
        r
        for m in (
            "fleet.vehicle.odometer",
            "fleet.vehicle.log.contract",
            "fleet.vehicle.log.services",
        )
        for r in (
            {
                "name": f"{m}: Fleet Manager full",
                "model": m,
                "domain": [[1, "=", 1]],
                "groups": ["Fleet Manager"],
                "perms": "rwck",
            },
            {
                "name": f"{m}: HR Officer read",
                "model": m,
                "domain": [[1, "=", 1]],
                "groups": ["HR Officer"],
                "perms": "r",
            },
            rules.deny_all(m),
        )
    ],
    *[
        {
            "name": f"{m}: read (all)",
            "model": m,
            "domain": [[1, "=", 1]],
            "groups": ["HR Employee", "HR Officer", "Fleet Manager"],
            "perms": "r",
        }
        for m in ("fleet.vehicle.model.brand", "fleet.vehicle.model")
    ],
    *[
        {
            "name": f"{m}: write (Fleet Manager)",
            "model": m,
            "domain": [[1, "=", 1]],
            "groups": ["Fleet Manager"],
            "perms": "wck",
        }
        for m in ("fleet.vehicle.model.brand", "fleet.vehicle.model")
    ],
]

_BRANDS = {
    "Toyota": ["Corolla", "Hilux"],
    "Volkswagen": ["Golf", "Passat"],
    "Ford": ["Focus", "Transit"],
    "BMW": ["3 Series", "X3"],
    "Renault": ["Clio", "Kangoo"],
    "Hyundai": ["Tucson", "Elantra"],
}


async def seed_fleet_area(env: Any) -> None:
    async with env.dml_conn() as conn:
        has = await conn.execute(text("SELECT 1 FROM fleet_vehicle_model_brand LIMIT 1"))
        if has.fetchone():
            _log.info("fleet: brands already seeded; skipping")
            return

    from dodoo.addons.fleet.models.fleet_vehicle_model import (
        FleetVehicleModel,
        FleetVehicleModelBrand,
    )

    for brand, models in _BRANDS.items():
        bid = await FleetVehicleModelBrand.create(env, {"name": brand})
        for m in models:
            await FleetVehicleModel.create(env, {"name": m, "brand_id": bid})
    _log.info("fleet: seeded %d brands with models", len(_BRANDS))


seed.IR_MODELS.extend(_MODELS)
seed.INDEXES.extend(_INDEXES)
seed.AREA_SEEDS.append(seed_fleet_area)
rules.FLEET_RULES.extend(_RULES)
