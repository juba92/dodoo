"""Registry of ``ir.rule`` record rules for the Fleet addon (see contracts/security-groups.md).

Per-model rule specs are appended to :data:`FLEET_RULES` by the fleet model modules as US6 is
implemented; :func:`apply` seeds them after ``sync_ir_model``.
"""

from __future__ import annotations

from typing import Any

from dodoo.addons.fleet.security import GROUP_FLEET_MANAGER
from dodoo.addons.hr.security import GROUP_OFFICER, seed_rules

FLEET_RULES: list[dict[str, Any]] = []


def deny_all(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: deny by default",
        "model": model,
        "domain": [["id", "=", 0]],
        "groups": None,
        "perms": "rwck",
    }


def manager_full(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: Fleet Manager full (company scope)",
        "model": model,
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_FLEET_MANAGER],
        "perms": "rwck",
    }


def officer_read(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: HR Officer read (company scope)",
        "model": model,
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_OFFICER],
        "perms": "r",
    }


async def apply(env: Any) -> None:
    await seed_rules(env, FLEET_RULES)
