from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

# (code, name, currency_code, phone_code)
_COUNTRIES = [
    ("EG", "Egypt", "EGP", "20"),
    ("GB", "United Kingdom", "GBP", "44"),
    ("US", "United States", "USD", "1"),
    ("SA", "Saudi Arabia", "SAR", "966"),
    ("AE", "United Arab Emirates", "AED", "971"),
    ("FR", "France", "EUR", "33"),
    ("DE", "Germany", "EUR", "49"),
    ("IT", "Italy", "EUR", "39"),
    ("ES", "Spain", "EUR", "34"),
    ("JO", "Jordan", "JOD", "962"),
    ("LB", "Lebanon", "LBP", "961"),
    ("MA", "Morocco", "MAD", "212"),
    ("KW", "Kuwait", "KWD", "965"),
    ("QA", "Qatar", "QAR", "974"),
    ("BH", "Bahrain", "BHD", "973"),
    ("OM", "Oman", "OMR", "968"),
    ("TR", "Turkey", "TRY", "90"),
    ("GR", "Greece", "EUR", "30"),
    ("IN", "India", "INR", "91"),
    ("CN", "China", "CNY", "86"),
]


async def seed_countries(env: Environment) -> None:
    """Idempotently insert the seeded country list (keyed on ``code``)."""
    async with env.dml_conn() as conn:
        for code, name, currency_code, phone_code in _COUNTRIES:
            existing = await conn.execute(
                text("SELECT id FROM res_country WHERE code = :code"), {"code": code}
            )
            if existing.fetchone():
                continue
            await conn.execute(
                text(
                    "INSERT INTO res_country (code, name, currency_code, phone_code, active) "
                    "VALUES (:code, :name, :cc, :pc, TRUE)"
                ),
                {"code": code, "name": name, "cc": currency_code, "pc": phone_code},
            )
        await conn.commit()
    _log.info("Seeded res.country (%d countries)", len(_COUNTRIES))
