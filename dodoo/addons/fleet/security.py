"""Fleet security group + ``ir.rule`` seeding.

``Fleet Manager`` is independent of the HR group nesting (a fleet manager need not be an HR
user). ``HR Officer`` gets *read* access to fleet records through a dedicated rule, not group
membership. Rule seeding reuses ``dodoo.addons.hr.security.seed_rules``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from dodoo.addons.hr.security import seed_rules  # noqa: F401  (re-exported for fleet.data.rules)

GROUP_FLEET_MANAGER = "Fleet Manager"


async def seed_groups(env: Any) -> int:
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM res_groups WHERE name = :n"), {"n": GROUP_FLEET_MANAGER}
        )
        r = row.fetchone()
        if r:
            return r[0]
        ins = await conn.execute(
            text(
                "INSERT INTO res_groups (name, full_name, category, create_date, write_date) "
                "VALUES (:n, 'Fleet / Manager', 'Fleet', now(), now()) RETURNING id"
            ),
            {"n": GROUP_FLEET_MANAGER},
        )
        gid = ins.scalar_one()
        await conn.commit()
        return gid


async def assign_fleet_manager(env: Any, uid: int) -> None:
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "INSERT INTO res_users_groups_rel (user_id, group_id) "
                "SELECT :uid, id FROM res_groups WHERE name = :n ON CONFLICT DO NOTHING"
            ),
            {"uid": uid, "n": GROUP_FLEET_MANAGER},
        )
        await conn.commit()
