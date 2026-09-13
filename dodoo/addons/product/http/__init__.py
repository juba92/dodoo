"""Product REST action routes.

JSON-RPC ``execute_kw`` covers plain CRUD (categories, units of measure, templates, variants);
these routes cover the verbs that are not a plain write — attribute-line application (variant
(re)generation), catalog search, and unit-of-measure conversion.

Every route is ``auth="session"``; every body is parsed through a
``dodoo.addons.product.validators`` model (Pydantic v2, ``extra="forbid"``). The product catalog
carries no dedicated security group of its own (read access is open to any authenticated user;
write access is gated by the ``Inventory Manager`` group defined in ``dodoo.addons.stock.security``
via record rules seeded from ``dodoo.addons.stock.data.rules``).
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi.responses import JSONResponse

from dodoo.http.routing import MountRegistry
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/product/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="product_static",
)


def json_ok(result: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"result": result}, status_code=status_code)


def json_err(code: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status_code)


# Route modules import `json_ok` / `json_err` from here and register with `@route`.
from dodoo.addons.product.http import products  # noqa: E402,F401
