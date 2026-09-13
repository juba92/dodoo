"""Inventory security groups + `ir.rule` record-rule seeding (contracts/security-groups.md).

Groups: ``Inventory User`` ⊂ ``Inventory Manager``. Mirrors `hr/security.py`'s shape.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

_log = logging.getLogger(__name__)

GROUP_USER = "Inventory User"
GROUP_MANAGER = "Inventory Manager"

_GROUP_DEFS = [
    (GROUP_USER, "Inventory / User"),
    (GROUP_MANAGER, "Inventory / Manager"),
]

_ANCESTORS: dict[str, list[str]] = {
    "user": [GROUP_USER],
    "manager": [GROUP_USER, GROUP_MANAGER],
}


async def seed_groups(env: Any) -> dict[str, int]:
    """Create the two Inventory groups if absent; return ``{name: id}``."""
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
                    "VALUES (:n, :f, 'Inventory', now(), now()) RETURNING id"
                ),
                {"n": name, "f": full},
            )
            ids[name] = ins.scalar_one()
        await conn.commit()
    return ids


async def assign_inventory_group(env: Any, uid: int, level: str) -> None:
    """Grant ``level`` ∈ {user, manager} plus every ancestor group."""
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


async def seed_rules(env: Any, rules: list[dict[str, Any]]) -> None:
    """Idempotently seed ``ir.rule`` rows (identical shape to `hr.security.seed_rules`)."""
    async with env.dml_conn() as conn:
        for spec in rules:
            if spec is None:
                continue
            exists = await conn.execute(
                text("SELECT id FROM ir_rule WHERE name = :n"), {"n": spec["name"]}
            )
            if exists.fetchone():
                continue
            model_row = await conn.execute(
                text("SELECT id FROM ir_model WHERE name = :m"), {"m": spec["model"]}
            )
            m = model_row.fetchone()
            if not m:
                _log.warning("seed_rules: ir_model missing for %s", spec["model"])
                continue
            perms = spec.get("perms", "rwck")
            rule_id = (
                await conn.execute(
                    text(
                        "INSERT INTO ir_rule "
                        "(name, model_id, domain_filter, perm_read, perm_write, perm_create, "
                        " perm_unlink, global_rule, create_date, write_date) "
                        "VALUES (:n, :mid, :dom, :pr, :pw, :pc, :pk, :glob, now(), now()) "
                        "RETURNING id"
                    ),
                    {
                        "n": spec["name"],
                        "mid": m[0],
                        "dom": json.dumps(spec["domain"]),
                        "pr": "r" in perms,
                        "pw": "w" in perms,
                        "pc": "c" in perms,
                        "pk": "k" in perms,
                        "glob": spec.get("groups") is None,
                    },
                )
            ).scalar_one()
            for gname in spec.get("groups") or []:
                await conn.execute(
                    text(
                        "INSERT INTO ir_rule_group_rel (rule_id, group_id) "
                        "SELECT :rid, id FROM res_groups WHERE name = :g "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"rid": rule_id, "g": gname},
                )
        await conn.commit()
