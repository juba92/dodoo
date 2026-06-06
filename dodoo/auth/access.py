from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.exceptions import AccessError

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class AccessEnforcer:
    @staticmethod
    async def get_applicable_rules(
        env: Environment,
        model_name: str,
        uid: int,
        operation: str,
    ) -> list[list]:
        perm_col = f"perm_{operation}"
        async with env.dml_conn() as conn:
            # Get user's group IDs
            result = await conn.execute(
                text("SELECT group_id FROM res_users_groups_rel WHERE user_id = :uid"),
                {"uid": uid},
            )
            group_ids = [row[0] for row in result]

            # Get applicable ir.rule rows
            if group_ids:
                result = await conn.execute(
                    text(
                        f"SELECT r.domain_filter FROM ir_rule r "
                        f"LEFT JOIN ir_rule_group_rel rg ON rg.rule_id = r.id "
                        f"JOIN ir_model m ON m.id = r.model_id "
                        f"WHERE m.name = :model "
                        f"AND r.{perm_col} = TRUE "
                        f"AND (r.global_rule = TRUE OR rg.group_id = ANY(:gids))"
                    ),
                    {"model": model_name, "gids": group_ids},
                )
            else:
                result = await conn.execute(
                    text(
                        f"SELECT r.domain_filter FROM ir_rule r "
                        f"JOIN ir_model m ON m.id = r.model_id "
                        f"WHERE m.name = :model "
                        f"AND r.{perm_col} = TRUE "
                        f"AND r.global_rule = TRUE"
                    ),
                    {"model": model_name},
                )

            domains = []
            for row in result:
                try:
                    domain = json.loads(row[0])
                    if isinstance(domain, list):
                        domains.append(domain)
                except (json.JSONDecodeError, TypeError):
                    pass

        return domains

    @staticmethod
    async def get_merged_domain(
        env: Environment,
        model_name: str,
        uid: int,
        operation: str,
    ) -> list | None:
        try:
            domains = await AccessEnforcer.get_applicable_rules(env, model_name, uid, operation)
        except Exception:
            return None

        if not domains:
            return None

        if len(domains) == 1:
            return domains[0]

        # AND-merge all domains
        merged: list = ["&"]
        for domain in domains:
            merged.extend(domain)
        return merged

    @staticmethod
    async def check_write_access(
        env: Environment,
        model_name: str,
        uid: int,
        operation: str,
    ) -> None:
        domains = await AccessEnforcer.get_applicable_rules(env, model_name, uid, operation)
        if domains:
            # If any deny rule exists (domain that would exclude the record), raise AccessError
            # Simplified: if any write-deny rules exist for this model+uid, raise
            raise AccessError(
                f"Access denied: operation '{operation}' on model '{model_name}' is restricted"
            )
