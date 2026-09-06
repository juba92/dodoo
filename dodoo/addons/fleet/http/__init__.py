"""Fleet REST action routes (vehicle state, driver assignment, alerts, cron)."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi.responses import JSONResponse

from dodoo.http.routing import MountRegistry
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
