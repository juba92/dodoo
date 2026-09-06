"""US6 — odometer: latest reading, lower-than-prior flagged (needs Postgres)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def vehicle(env, company_id):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
    from dodoo.addons.fleet.models.fleet_vehicle_model import (
        FleetVehicleModel,
        FleetVehicleModelBrand,
    )

    b = await FleetVehicleModelBrand.create(env, {"name": "OB"})
    m = await FleetVehicleModel.create(env, {"name": "OM", "brand_id": b})
    return await FleetVehicle.create(env, {"model_id": m, "company_id": company_id})


async def test_latest_reading_and_computed_field(env, vehicle):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
    from dodoo.addons.fleet.models.fleet_vehicle_odometer import FleetVehicleOdometer

    await FleetVehicleOdometer.create(env, {"vehicle_id": vehicle, "value": 1000, "date": "2026-01-01"})
    await FleetVehicleOdometer.create(env, {"vehicle_id": vehicle, "value": 2500, "date": "2026-03-01"})
    latest = await FleetVehicleOdometer.latest_for(env, vehicle)
    assert latest["value"] == 2500
    v = await FleetVehicle.read(env, [vehicle], ["odometer"])
    assert v[0]["odometer"] == 2500


async def test_lower_reading_accepted_but_flagged(env, vehicle):
    from dodoo.addons.fleet.models.fleet_vehicle_odometer import FleetVehicleOdometer

    await FleetVehicleOdometer.create(env, {"vehicle_id": vehicle, "value": 5000, "date": "2026-01-01"})
    low_id = await FleetVehicleOdometer.create(
        env, {"vehicle_id": vehicle, "value": 4000, "date": "2026-02-01"}
    )
    rows = await FleetVehicleOdometer.read(env, [low_id], ["inconsistent"])
    assert rows[0]["inconsistent"] is True
