"""Inventory Accounting REST action routes: category valuation configuration + reporting."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def json_ok(result: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"result": result}, status_code=status_code)


def json_err(code: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status_code)


from dodoo.addons.stock_account.http import valuation  # noqa: E402,F401
