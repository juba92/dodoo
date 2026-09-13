from __future__ import annotations

from typing import Any

from dodoo.addons.stock.security import seed_groups


async def seed(env: Any) -> None:
    await seed_groups(env)
