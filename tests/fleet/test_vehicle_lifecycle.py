"""US6 — vehicle state machine, brand derivation, driver history (needs Postgres)."""

from __future__ import annotations

import pytest

from dodoo.addons.fleet.models.fleet_vehicle import _STATE_VALUES
from dodoo.core.exceptions import DodooError


def test_seven_states():
    assert _STATE_VALUES == {
        "new_request", "to_order", "ordered", "registered",
        "downgraded", "reserved", "waiting_list",
    }


@pytest.fixture
async def fleet(env, company_id):

    from dodoo.addons.fleet.models.fleet_vehicle_model import (
        FleetVehicleModel,
        FleetVehicleModelBrand,
    )
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    bid = await FleetVehicleModelBrand.create(env, {"name": "TestBrand"})
    mid = await FleetVehicleModel.create(env, {"name": "TestModel", "brand_id": bid})
    drv = await HrEmployee.create(env, {"name": "Driver", "company_id": company_id})
    drv2 = await HrEmployee.create(env, {"name": "Driver2", "company_id": company_id})
    return {"brand": bid, "model": mid, "company_id": company_id, "drv": drv, "drv2": drv2}


async def test_create_derives_brand_and_name(env, fleet):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle

    vid = await FleetVehicle.create(
        env, {"model_id": fleet["model"], "company_id": fleet["company_id"], "license_plate": "AB-123"}
    )
    rows = await FleetVehicle.read(env, [vid], ["brand_id", "name", "state"])
    assert rows[0]["brand_id"] == fleet["brand"]
    assert "TestBrand" in rows[0]["name"] and "AB-123" in rows[0]["name"]
    assert rows[0]["state"] == "new_request"


async def test_state_machine_and_conflict(env, fleet):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle

    vid = await FleetVehicle.create(env, {"model_id": fleet["model"], "company_id": fleet["company_id"]})
    await FleetVehicle.action_set_state(env, [vid], "to_order", uid=1)
    await FleetVehicle.action_set_state(env, [vid], "ordered", uid=1)
    with pytest.raises(DodooError, match="vehicle_state_conflict"):
        await FleetVehicle.action_set_state(env, [vid], "registered", uid=1, expected_state="to_order")
    with pytest.raises(DodooError, match="vehicle_state_invalid"):
        await FleetVehicle.action_set_state(env, [vid], "flying", uid=1)


async def test_driver_history_retained(env, fleet):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle

    vid = await FleetVehicle.create(env, {"model_id": fleet["model"], "company_id": fleet["company_id"]})
    await FleetVehicle.assign_driver(env, vid, fleet["drv"], uid=1)
    await FleetVehicle.assign_driver(env, vid, fleet["drv2"], uid=1)
    rows = await FleetVehicle.read(env, [vid], ["driver_id", "former_driver_ids"])
    assert rows[0]["driver_id"] == fleet["drv2"]
    assert fleet["drv"] in (rows[0]["former_driver_ids"] or [])
    assigned = await FleetVehicle.get_assigned(env, fleet["drv2"])
    assert any(a["id"] == vid for a in assigned)


async def test_archived_driver_flags_reassignment(env, fleet):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    vid = await FleetVehicle.create(env, {"model_id": fleet["model"], "company_id": fleet["company_id"]})
    await FleetVehicle.assign_driver(env, vid, fleet["drv"], uid=1)
    await HrEmployee.write(env, [fleet["drv"]], {"active": False})
    res = await FleetVehicle.flag_reassignment_for_archived_drivers(env)
    assert res["flagged"] == 1
    rows = await FleetVehicle.read(env, [vid], ["needs_reassignment"])
    assert rows[0]["needs_reassignment"] is True
