from __future__ import annotations

import logging
import pathlib

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from dodoo.addons.localization.i18n import catalog
from dodoo.addons.localization.locale import locale_meta
from dodoo.http.routing import MountRegistry, route

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/localization/static",
    StaticFiles(directory=str(_STATIC_DIR)),
    name="localization_static",
)

_log = logging.getLogger(__name__)


@route("/web/i18n/{lang}.json", methods=["GET"], auth="public")
async def i18n_catalog(request: Request, lang: str) -> JSONResponse:
    """Client-string catalog + locale metadata for one installed language.

    400 for an unknown/inactive language; 503 if the language table can't be read.
    """
    env = request.app.state.env
    try:
        meta = await locale_meta(env, lang)
    except Exception:
        _log.exception("i18n catalog: res_lang read failed")
        return JSONResponse(
            {"status": "degraded", "db": "disconnected"}, status_code=503
        )

    if meta is None:
        return JSONResponse(
            {"error": "unknown_language", "detail": f"no active res.lang with code {lang!r}"},
            status_code=400,
        )

    meta["terms"] = catalog(lang)
    return JSONResponse(meta)
