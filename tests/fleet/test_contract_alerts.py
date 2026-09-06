"""US6 — leasing/insurance contract expiry alerts (FR-056, ADR-027, needs Postgres)."""

from __future__ import annotations

import datetime

import pytest

from dodoo.addons.fleet.models.fleet_vehicle_log_contract import FLEET_ALERT_WINDOW_DAYS
from dodoo.core.exceptions import DodooError


def test_default_window():
    assert FLEET_ALERT_WINDOW_DAYS == 30


@pytest.fixture
async def vehicle(env, company_id):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
    from dodoo.addons.fleet.models.fleet_vehicle_model import (
        FleetVehicleModel,
        FleetVehicleModelBrand,
    )

    b = await FleetVehicleModelBrand.create(env, {"name": "CB"})
    m = await FleetVehicleModel.create(env, {"name": "CM", "brand_id": b})
    return await FleetVehicle.create(env, {"model_id": m, "company_id": company_id})


async def test_alert_lists_soon_and_overdue(env, vehicle):
    from dodoo.addons.fleet.models.fleet_vehicle_log_contract import FleetVehicleLogContract

    today = datetime.date.today()
    soon = (today + datetime.timedelta(days=10)).isoformat()
    past = (today - datetime.timedelta(days=30)).isoformat()
    far = (today + datetime.timedelta(days=200)).isoformat()

    await FleetVehicleLogContract.create(
        env, {"vehicle_id": vehicle, "cost_type": "insurance", "start_date": "2026-01-01", "expiration_date": soon}
    )
    await FleetVehicleLogContract.create(
        env, {"vehicle_id": vehicle, "cost_type": "leasing", "start_date": "2025-01-01", "expiration_date": past}
    )
    await FleetVehicleLogContract.create(
        env, {"vehicle_id": vehicle, "cost_type": "leasing", "start_date": "2026-01-01", "expiration_date": far}
    )

    alerts = await FleetVehicleLogContract.get_expiry_alerts(env)
    exps = {a["expiration_date"] for a in alerts}
    assert soon in exps and past in exps and far not in exps
    by_exp = {a["expiration_date"]: a for a in alerts}
    assert by_exp[soon]["days_left"] == 10
    assert by_exp[past]["days_left"] == -30


async def test_run_expiry_flips_state_idempotently(env, vehicle):
    from dodoo.addons.fleet.models.fleet_vehicle_log_contract import FleetVehicleLogContract

    past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    cid = await FleetVehicleLogContract.create(
        env, {"vehicle_id": vehicle, "cost_type": "leasing", "start_date": "2025-01-01", "expiration_date": past}
    )
    first = await FleetVehicleLogContract.run_fleet_contract_expiry(env)
    assert first["expired"] == 1
    second = await FleetVehicleLogContract.run_fleet_contract_expiry(env)
    assert second["expired"] == 0
    rows = await FleetVehicleLogContract.read(env, [cid], ["state"])
    assert rows[0]["state"] == "expired"


async def test_bad_dates_rejected(env, vehicle):
    from dodoo.addons.fleet.models.fleet_vehicle_log_contract import FleetVehicleLogContract

    with pytest.raises(DodooError, match="fleet_contract_dates"):
        await FleetVehicleLogContract.create(
            env,
            {"vehicle_id": vehicle, "cost_type": "leasing", "start_date": "2026-06-01", "expiration_date": "2026-01-01"},
        )
