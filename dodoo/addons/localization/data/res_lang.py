from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

# (code, name, direction, decimal_point, thousands_sep, grouping, date_format)
_LANGS = [
    ("en", "English", "ltr", ".", ",", "[3,0]", "%m/%d/%Y"),
    ("ar", "العربية", "rtl", ".", ",", "[3,0]", "%d/%m/%Y"),
]


async def seed_langs(env: Environment) -> None:
    """Idempotently insert the two installed languages (keyed on ``code``)."""
    async with env.dml_conn() as conn:
        for code, name, direction, dp, ts, grouping, date_format in _LANGS:
            existing = await conn.execute(
                text("SELECT id FROM res_lang WHERE code = :code"), {"code": code}
            )
            if existing.fetchone():
                continue
            await conn.execute(
                text(
                    "INSERT INTO res_lang "
                    "(code, name, direction, decimal_point, thousands_sep, grouping, "
                    " date_format, active) "
                    "VALUES (:code, :name, :direction, :dp, :ts, :grouping, :df, TRUE)"
                ),
                {
                    "code": code,
                    "name": name,
                    "direction": direction,
                    "dp": dp,
                    "ts": ts,
                    "grouping": grouping,
                    "df": date_format,
                },
            )
        await conn.commit()
    _log.info("Seeded res.lang (en, ar)")
