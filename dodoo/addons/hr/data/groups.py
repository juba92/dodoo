"""Seed the HR security groups (delegates to ``dodoo.addons.hr.security``)."""

from __future__ import annotations

from typing import Any

from dodoo.addons.hr.security import seed_groups


async def seed(env: Any) -> dict[str, int]:
    return await seed_groups(env)
