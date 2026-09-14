from __future__ import annotations

import pathlib

from fastapi import Request
from fastapi.responses import HTMLResponse

from dodoo.http.routing import MountRegistry, route
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
_INDEX = _STATIC_DIR / "index.html"


@route("/web/client", methods=["GET"], auth="public")
async def web_client(request: Request) -> HTMLResponse:
    # Never let a browser pin the SPA shell (it links the entry script, so a stale
    # copy freezes the whole client) — NoCacheStaticFiles already sends
    # Cache-Control: no-cache on every /web/static/* file, app.js included, so a
    # browser always revalidates it. Do NOT also query-string-bust the entry
    # <script src="/web/static/app.js"> here: every other file in the app imports
    # App via that exact literal, unversioned path (`import { App } from
    # '/web/static/app.js'`), and a browser treats a query-string variant as a
    # completely different module URL — the entry tag and every dynamic import
    # would then load and evaluate app.js as two separate, un-synchronized
    # module instances (each with its own App.state and its own 'hashchange'
    # listener), racing on every navigation.
    html = _INDEX.read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


MountRegistry.get().add_mount(
    "/web/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="web_static",
)
