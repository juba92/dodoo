from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.addons.localization.data.res_country import seed_countries
from dodoo.addons.localization.data.res_country_state import seed_states
from dodoo.addons.localization.data.res_lang import seed_langs
from dodoo.addons.localization.service import apply_country_localization

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

# Account-referencing company columns — added here (not on the base model class) so
# `base` keeps no dependency on `account` (ADR-005 / mirrors _PARTNER_FK_COLUMNS).
_COMPANY_FK_COLUMNS = [
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS default_sale_tax_id INTEGER",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS default_purchase_tax_id INTEGER",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS default_fiscal_position_id INTEGER",
]


async def seed_localization_data(env: Environment) -> None:
    async with env.dml_conn() as conn:
        for ddl in _COMPANY_FK_COLUMNS:
            await conn.execute(text(ddl))
        # System default language is Arabic (FR-002); backfill any pre-existing row.
        await conn.execute(
            text("UPDATE res_company SET lang = 'ar' WHERE lang IS NULL OR lang = ''")
        )
        await conn.commit()

    await seed_langs(env)
    await seed_countries(env)
    await seed_states(env)

    # Fresh install: no country chosen yet → default the company to Egypt and apply
    # the Egypt package (EGP + taxes + fiscal positions + defaults). FR-016 / FR-025.
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id, country_id FROM res_company ORDER BY id LIMIT 1")
        )
        r = row.fetchone()
    if not r:
        _log.warning("localization: no company found; skipping country seed")
        return
    company_id, country_id = r[0], r[1]
    if country_id is not None:
        _log.info("localization: company already has a country; skipping Egypt seed")
        return

    result = await apply_country_localization(env, company_id, "EG")
    _log.info("localization: fresh-install Egypt package -> %s", result)
