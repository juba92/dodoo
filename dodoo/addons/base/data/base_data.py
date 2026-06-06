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

    # Idempotent: skip if admin user already exists
    async with env.dml_conn() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM res_users"))
        count = result.scalar_one()
        if count > 0:
            _log.info("Base data already seeded; skipping")
            return

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
