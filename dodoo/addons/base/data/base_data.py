from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


async def seed_base_data(env: Environment) -> None:
    from dodoo.addons.base.models.res_groups import ResGroups
    from dodoo.addons.base.models.res_users import ResUsers

    # Idempotent: only create admin user if not present
    async with env.dml_conn() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM res_users"))
        count = result.scalar_one()

    if count == 0:
        # Create Administrator group
        group_id = await ResGroups.create(
            env,
            {"name": "Administrator", "full_name": "Technical / Administrator"},
        )

        # Create admin user with Argon2id-hashed password
        password_hash = ResUsers._hash_password("admin")
        user_id = await ResUsers.create(
            env,
            {
                "login": "admin",
                "password_hash": password_hash,
                "name": "Administrator",
                "active": True,
            },
        )

        # Link admin user to Administrator group via junction table
        async with env.dml_conn() as conn:
            await conn.execute(
                text(
                    "INSERT INTO res_users_groups_rel (user_id, group_id) VALUES (:uid, :gid) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"uid": user_id, "gid": group_id},
            )
            await conn.commit()

        _log.info("Seeded base data: admin user and Administrator group")
    else:
        _log.info("Admin user already exists; skipping user seed")

    # Always run currency/company seed — idempotent internally
    await _seed_currency_and_company(env)


async def _seed_currency_and_company(env: Environment) -> None:
    from dodoo.addons.base.models.res_company import ResCompany
    from dodoo.addons.base.models.res_currency import ResCurrency

    async with env.dml_conn() as conn:
        result = await conn.execute(text("SELECT id FROM res_currency WHERE code = 'EUR' LIMIT 1"))
        row = result.fetchone()
        currency_id = row[0] if row else None

    if currency_id is None:
        currency_id = await ResCurrency.create(
            env,
            {"code": "EUR", "name": "Euro", "symbol": "€", "rounding": 2, "active": True},
        )
        _log.info("Seeded EUR currency")
    else:
        _log.info("Currency EUR already exists; skipping")

    async with env.dml_conn() as conn:
        result = await conn.execute(text("SELECT id FROM res_company LIMIT 1"))
        if result.fetchone():
            _log.info("Default company already exists; skipping")
            return

    await ResCompany.create(
        env,
        {"name": "My Company", "currency_id": currency_id},
    )

    _log.info("Seeded base data: default company")
