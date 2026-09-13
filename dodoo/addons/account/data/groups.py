from __future__ import annotations

from dodoo.addons.account.security import seed_groups as _seed_groups


async def seed_groups(env) -> None:
    await _seed_groups(env)
