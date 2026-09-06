"""Seed the Fleet Manager group (delegates to ``dodoo.addons.fleet.security``)."""

from __future__ import annotations

from typing import Any

from dodoo.addons.fleet.security import seed_groups


async def seed(env: Any) -> int:
    return await seed_groups(env)
