import json
from typing import Any

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Many2many, Many2one, Text
from dodoo.core.models import BaseModel


class IrRule(BaseModel):
    _name = "ir.rule"

    name = Char(size=256, required=True)
    model_id = Many2one("ir.model", required=True)
    domain_filter = Text(required=True)
    perm_read = Boolean(default=True)
    perm_write = Boolean(default=True)
    perm_create = Boolean(default=True)
    perm_unlink = Boolean(default=True)
    global_rule = Boolean(default=False)
    # Explicit junction columns so the table matches AccessEnforcer's query
    # (`rg.rule_id` / `rg.group_id`); without these the MigrationRunner would name
    # the columns `ir_rule_id` / `res_groups_id` and every group-scoped rule would
    # silently fail its join (→ get_merged_domain returns None → access allowed).
    group_ids = Many2many(
        "res.groups",
        relation_table="ir_rule_group_rel",
        column1="rule_id",
        column2="group_id",
    )

    @classmethod
    async def write(cls, env: Any, ids: list[int], vals: dict[str, Any]) -> bool:
        if "domain_filter" in vals:
            _validate_domain(vals["domain_filter"])
        return await super().write(env, ids, vals)

    @classmethod
    async def create(cls, env: Any, vals: dict[str, Any]) -> int:
        if "domain_filter" in vals:
            _validate_domain(vals["domain_filter"])
        return await super().create(env, vals)


def _validate_domain(domain_filter: str) -> None:
    try:
        parsed = json.loads(domain_filter)
    except (json.JSONDecodeError, TypeError) as exc:
        raise DodooError(f"domain_filter must be valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise DodooError("domain_filter must be a JSON array")
