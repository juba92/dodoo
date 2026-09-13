"""Accounting security groups (contracts/coa-journals-audit-trail.md, ADR-039).

``account`` has no group of its own before this feature (research.md D8) — every pre-existing
route stays session-only. These two groups gate only the new sensitive actions this feature adds
(lock-exception grant/revoke, hash-chain-mode toggle, fiscal-year close): "Accounting Manager"
for those; "Accounting User" exists for symmetry with every other addon's two-tier pattern
(``hr``/``product``/``stock``) but is not currently required by any route.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

GROUP_USER = "Accounting User"
GROUP_MANAGER = "Accounting Manager"

_GROUP_DEFS = [
    (GROUP_USER, "Accounting / User"),
    (GROUP_MANAGER, "Accounting / Manager"),
]

_ANCESTORS: dict[str, list[str]] = {
    "user": [GROUP_USER],
    "manager": [GROUP_USER, GROUP_MANAGER],
}


async def seed_groups(env: Any) -> dict[str, int]:
    """Create the two Accounting groups if absent; return ``{name: id}``."""
    ids: dict[str, int] = {}
    async with env.dml_conn() as conn:
        for name, full in _GROUP_DEFS:
            row = await conn.execute(
                text("SELECT id FROM res_groups WHERE name = :n"), {"n": name}
            )
            r = row.fetchone()
            if r:
                ids[name] = r[0]
                continue
            ins = await conn.execute(
                text(
                    "INSERT INTO res_groups (name, full_name, category, create_date, write_date) "
                    "VALUES (:n, :f, 'Accounting', now(), now()) RETURNING id"
                ),
                {"n": name, "f": full},
            )
            ids[name] = ins.scalar_one()
        await conn.commit()
    return ids


async def assign_accounting_group(env: Any, uid: int, level: str) -> None:
    """Grant ``level`` in {user, manager} plus every ancestor group."""
    names = _ANCESTORS[level]
    async with env.dml_conn() as conn:
        for name in names:
            await conn.execute(
                text(
                    "INSERT INTO res_users_groups_rel (user_id, group_id) "
                    "SELECT :uid, id FROM res_groups WHERE name = :n "
                    "ON CONFLICT DO NOTHING"
                ),
                {"uid": uid, "n": name},
            )
        await conn.commit()
