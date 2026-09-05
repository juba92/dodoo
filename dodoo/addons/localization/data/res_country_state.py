from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

# Minimal representative reference set — Egyptian governorates.
# (country_code, state_code, name)
_STATES = [
    ("EG", "C", "Cairo"),
    ("EG", "GZ", "Giza"),
    ("EG", "ALX", "Alexandria"),
    ("EG", "DK", "Dakahlia"),
    ("EG", "SHR", "Sharqia"),
    ("EG", "KB", "Qalyubia"),
]


async def seed_states(env: Environment) -> None:
    """Idempotently insert country states (keyed on country + code)."""
    async with env.dml_conn() as conn:
        for country_code, state_code, name in _STATES:
            country = await conn.execute(
                text("SELECT id FROM res_country WHERE code = :code"),
                {"code": country_code},
            )
            crow = country.fetchone()
            if not crow:
                continue
            country_id = crow[0]
            existing = await conn.execute(
                text(
                    "SELECT id FROM res_country_state "
                    "WHERE country_id = :cid AND code = :code"
                ),
                {"cid": country_id, "code": state_code},
            )
            if existing.fetchone():
                continue
            await conn.execute(
                text(
                    "INSERT INTO res_country_state (country_id, code, name) "
                    "VALUES (:cid, :code, :name)"
                ),
                {"cid": country_id, "code": state_code, "name": name},
            )
        await conn.commit()
    _log.info("Seeded res.country.state (%d states)", len(_STATES))
