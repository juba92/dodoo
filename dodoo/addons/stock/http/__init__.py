"""Inventory REST action routes.

JSON-RPC ``execute_kw`` covers plain CRUD; these routes cover the workflow verbs that are not a
plain write — warehouse topology, transfer confirm/validate/cancel/return, inventory counts,
traceability, putaway/route/reordering actions, and scrap confirmation.

Every route is ``auth="session"`` and re-checks the caller's Inventory groups server-side
(``dodoo.addons.stock.validators.require_groups``); every body is parsed through a
``dodoo.addons.stock.validators`` model (Pydantic v2, ``extra="forbid"``).
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi.responses import JSONResponse

from dodoo.http.routing import MountRegistry
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/stock/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="stock_static",
)


def json_ok(result: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"result": result}, status_code=status_code)


def json_err(code: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status_code)


# Route modules import `json_ok` / `json_err` from here and register with `@route`.
from dodoo.addons.stock.http import (  # noqa: E402,F401
    inventory,
    routes,
    scrap,
    traceability,
    transfers,
    warehouses,
)
