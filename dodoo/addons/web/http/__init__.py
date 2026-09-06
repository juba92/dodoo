from __future__ import annotations

import pathlib

from fastapi import Request
from fastapi.responses import FileResponse

from dodoo.http.routing import MountRegistry, route
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"


@route("/web/client", methods=["GET"], auth="public")
async def web_client(request: Request) -> FileResponse:
    # Never let a browser pin the SPA shell: it links the entry script, so a stale
    # copy freezes the whole client on an old bundle.
    return FileResponse(
        _STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"}
    )


MountRegistry.get().add_mount(
    "/web/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="web_static",
)
