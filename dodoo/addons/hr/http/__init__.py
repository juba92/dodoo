"""HR REST action routes.

JSON-RPC ``execute_kw`` covers plain CRUD and read-side helpers (the SPA already speaks it);
these routes cover the workflow verbs that are not a plain write — contract state changes,
leave approval, applicant stage moves, applicant→employee conversion, appraisal lifecycle,
referral submission, and the idempotent ``/hr/cron/*`` advancers.

Every route is ``auth="session"`` and re-checks the caller's HR groups server-side
(``dodoo.addons.hr.validators.require_groups``); every body is parsed through a
``dodoo.addons.hr.validators`` model (Pydantic v2, ``extra="forbid"``).
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi.responses import JSONResponse

from dodoo.http.routing import MountRegistry
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/hr/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="hr_static",
)


def json_ok(result: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"result": result}, status_code=status_code)


def json_err(code: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status_code)


# Route modules import `json_ok` / `json_err` from here and register with `@route`.
from dodoo.addons.hr.http import employees, timeoff  # noqa: E402,F401
