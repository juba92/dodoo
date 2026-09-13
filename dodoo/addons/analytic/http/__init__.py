from __future__ import annotations

import logging
import pathlib

from dodoo.http.routing import MountRegistry
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/analytic/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="analytic_static",
)

_log = logging.getLogger(__name__)

# CRUD for analytic.plan / analytic.account is generic JSON-RPC dispatch
# (dodoo.http.jsonrpc) — no dedicated REST routes are needed.
