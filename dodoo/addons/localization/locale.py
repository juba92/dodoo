"""Server-side locale metadata helpers.

Reads the format fields of a ``res.lang`` row so the ``/web/i18n/{lang}.json`` endpoint can
hand the SPA everything it needs to format numbers and dates identically to the server.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from dodoo import Environment

_DEFAULTS = {
    "direction": "ltr",
    "date_format": "%d/%m/%Y",
    "decimal_point": ".",
    "thousands_sep": ",",
    "grouping": [3, 0],
}


def _parse_grouping(raw: str | None) -> list[int]:
    try:
        val = json.loads(raw) if raw else None
        if isinstance(val, list) and all(isinstance(n, int) for n in val):
            return val
    except (ValueError, TypeError):
        pass
    return [3, 0]


async def locale_meta(env: Environment, lang: str) -> dict[str, Any] | None:
    """Return locale metadata for an active language code, or None if not installed."""
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT code, name, direction, decimal_point, thousands_sep, grouping, "
                "date_format FROM res_lang WHERE code = :code AND active = TRUE"
            ),
            {"code": lang},
        )
        r = row.mappings().fetchone()
    if r is None:
        return None
    return {
        "lang": r["code"],
        "name": r["name"],
        "direction": r["direction"] or _DEFAULTS["direction"],
        "date_format": r["date_format"] or _DEFAULTS["date_format"],
        "decimal_point": r["decimal_point"] or _DEFAULTS["decimal_point"],
        "thousands_sep": r["thousands_sep"] or _DEFAULTS["thousands_sep"],
        "grouping": _parse_grouping(r["grouping"]),
    }
