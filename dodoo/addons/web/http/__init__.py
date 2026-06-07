from __future__ import annotations

import pathlib

from fastapi import Request
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from dodoo.http.routing import MountRegistry, route

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"


@route("/web/client", methods=["GET"], auth="public")
async def web_client(request: Request) -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


MountRegistry.get().add_mount(
    "/web/static",
    StaticFiles(directory=str(_STATIC_DIR)),
    name="web_static",
)
