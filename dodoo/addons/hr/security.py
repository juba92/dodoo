"""HR security groups + ``ir.rule`` record-rule seeding (contracts/security-groups.md).

Groups: ``HR Employee`` ⊂ ``HR Officer`` ⊂ ``HR Administrator``. dodoo ``res.groups`` has no
implied-group graph, so nesting is materialised at assignment time by :func:`assign_hr_group`
(a user granted ``officer`` gets rows for ``HR Employee`` + ``HR Officer``).

Record rules are seeded from a list of dicts by :func:`seed_rules`; per-model rule rows are
collected in ``dodoo/addons/hr/data/rules.py``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

_log = logging.getLogger(__name__)

GROUP_EMPLOYEE = "HR Employee"
GROUP_OFFICER = "HR Officer"
GROUP_ADMIN = "HR Administrator"

_GROUP_DEFS = [
    (GROUP_EMPLOYEE, "Human Resources / Employee"),
    (GROUP_OFFICER, "Human Resources / Officer"),
    (GROUP_ADMIN, "Human Resources / Administrator"),
]

# Ancestor chain for at-assignment nesting.
_ANCESTORS: dict[str, list[str]] = {
    "employee": [GROUP_EMPLOYEE],
    "officer": [GROUP_EMPLOYEE, GROUP_OFFICER],
    "administrator": [GROUP_EMPLOYEE, GROUP_OFFICER, GROUP_ADMIN],
}


async def seed_groups(env: Any) -> dict[str, int]:
    """Create the three HR groups if absent; return ``{name: id}``."""
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
                    "VALUES (:n, :f, 'Human Resources', now(), now()) RETURNING id"
                ),
                {"n": name, "f": full},
            )
            ids[name] = ins.scalar_one()
        await conn.commit()
    return ids


async def assign_hr_group(env: Any, uid: int, level: str) -> None:
    """Grant ``level`` ∈ {employee, officer, administrator} plus every ancestor group."""
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
    """Idempotently seed ``ir.rule`` rows.

    Each dict: ``{name, model, domain (list), groups (list[str]|None), perms (str, default
    "rwck")}``. ``groups=None`` → a global rule. ``perms`` chars: r/w/c/k.
    """
    async with env.dml_conn() as conn:
        for spec in rules:
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
