"""Fleet REST action routes (vehicle state, driver assignment, alerts, cron)."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from dodoo.http.routing import MountRegistry, route
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/fleet/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="fleet_static",
)


def json_ok(result: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"result": result}, status_code=status_code)


def json_err(code: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status_code)


# ---- routes ----------------------------------------------------------------

from dodoo.addons.fleet.security import GROUP_FLEET_MANAGER  # noqa: E402
from dodoo.addons.fleet.validators import (  # noqa: E402
    AssignDriver,
    VehicleSetState,
    require_groups,
    validate,
)
from dodoo.core.context import get_uid  # noqa: E402
from dodoo.core.exceptions import AccessError, DodooError  # noqa: E402


@route("/fleet/vehicle/{vehicle_id}/set-state", methods=["POST"], auth="session")
async def vehicle_set_state(request: Request, vehicle_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(VehicleSetState, await request.json())
        await require_groups(env, uid, GROUP_FLEET_MANAGER)
        from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle

        return json_ok(
            await FleetVehicle.action_set_state(
                env, [vehicle_id], payload.state, uid=uid,
                expected_state=payload.expected_state,
            )
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/fleet/vehicle/{vehicle_id}/assign-driver", methods=["POST"], auth="session")
async def vehicle_assign_driver(request: Request, vehicle_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(AssignDriver, await request.json())
        await require_groups(env, uid, GROUP_FLEET_MANAGER)
        from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle

        return json_ok(
            await FleetVehicle.assign_driver(env, vehicle_id, payload.driver_id, uid)
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/fleet/alerts", methods=["GET"], auth="session")
async def fleet_alerts(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_FLEET_MANAGER, "HR Officer")
        from dodoo.addons.fleet.models.fleet_vehicle_log_contract import (
            FleetVehicleLogContract,
        )

        wd = request.query_params.get("window_days")
        return json_ok(
            await FleetVehicleLogContract.get_expiry_alerts(
                env, int(wd) if wd else None
            )
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/fleet/cron/contract-expiry", methods=["POST"], auth="session")
async def cron_contract_expiry(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_FLEET_MANAGER)
        from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
        from dodoo.addons.fleet.models.fleet_vehicle_log_contract import (
            FleetVehicleLogContract,
        )

        expired = await FleetVehicleLogContract.run_fleet_contract_expiry(env)
        flagged = await FleetVehicle.flag_reassignment_for_archived_drivers(env)
        return json_ok({**expired, **flagged})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
