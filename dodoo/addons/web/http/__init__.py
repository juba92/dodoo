from __future__ import annotations

import pathlib

from fastapi import Request
from fastapi.responses import HTMLResponse

from dodoo.http.routing import MountRegistry, route
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
_INDEX = _STATIC_DIR / "index.html"
_APP_JS = _STATIC_DIR / "app.js"


@route("/web/client", methods=["GET"], auth="public")
async def web_client(request: Request) -> HTMLResponse:
    # Never let a browser pin the SPA shell (it links the entry script, so a stale
    # copy freezes the whole client), and stamp app.js with its own mtime so a
    # rebuilt bundle is always a new URL even if the browser ignores no-cache.
    html = _INDEX.read_text(encoding="utf-8")
    try:
        ver = str(int(_APP_JS.stat().st_mtime))
        html = html.replace("/web/static/app.js", f"/web/static/app.js?v={ver}")
    except OSError:
        pass
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


MountRegistry.get().add_mount(
    "/web/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="web_static",
)
