"""US6 — Fleet record rules: Manager full, Officer read, driver reads own (needs Postgres)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def scene(env, company_id):
    from sqlalchemy import text

    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
    from dodoo.addons.fleet.models.fleet_vehicle_model import (
        FleetVehicleModel,
        FleetVehicleModelBrand,
    )
    from dodoo.addons.fleet.security import assign_fleet_manager
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        mgr_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('fm','FM',TRUE,now(),now()) RETURNING id"))).scalar_one()
        drv_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('fd','FD',TRUE,now(),now()) RETURNING id"))).scalar_one()
        out_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('fo','FO',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    await assign_fleet_manager(env, mgr_uid)
    await assign_hr_group(env, drv_uid, "employee")
    await assign_hr_group(env, out_uid, "employee")

    drv = await HrEmployee.create(env, {"name": "FD", "company_id": company_id, "user_id": drv_uid})
    b = await FleetVehicleModelBrand.create(env, {"name": "AB"})
    m = await FleetVehicleModel.create(env, {"name": "AM", "brand_id": b})
    mine = await FleetVehicle.create(env, {"model_id": m, "company_id": company_id, "driver_id": drv})
    other = await FleetVehicle.create(env, {"model_id": m, "company_id": company_id})
    return {"mgr_uid": mgr_uid, "drv_uid": drv_uid, "out_uid": out_uid, "mine": mine, "other": other}


async def test_manager_sees_all_driver_sees_own_outsider_none(env, scene):
    from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle

    mgr = await FleetVehicle.search(env, [], uid=scene["mgr_uid"])
    assert len(mgr) >= 2

    drv = await FleetVehicle.search(env, [], uid=scene["drv_uid"])
    assert drv == [scene["mine"]]

    outsider = await FleetVehicle.search(env, [], uid=scene["out_uid"])
    assert outsider == []
