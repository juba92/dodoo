from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.exceptions import AccessError

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


def _or_join(domains: list[list]) -> list:
    """Combine several domain lists with OR (prefix ``|`` for each pair after the first)."""
    if len(domains) == 1:
        return domains[0]
    out: list = []
    for _ in range(len(domains) - 1):
        out.append("|")
    for d in domains:
        out.extend(d)
    return out


class AccessEnforcer:
    @staticmethod
    async def build_context(env: Environment, uid: int) -> dict:
        """Values for ``$``-placeholder substitution in ir.rule domains (ADR-028).

        ``company_ids`` is every ``res.company`` id — one today; a ``res.users.company_ids``
        M2M replaces this when multi-company support lands.
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(text("SELECT id FROM res_company ORDER BY id"))
            company_ids = [r[0] for r in rows]
        return {
            "uid": uid,
            "company_ids": company_ids,
            "company_id": company_ids[0] if company_ids else None,
        }

    @staticmethod
    async def _fetch_rules(
        env: Environment, model_name: str, uid: int, operation: str
    ) -> tuple[list[list], list[list], bool]:
        """Return ``(global_domains, matching_group_domains, model_has_any_group_rule)``.

        Odoo semantics: global rules always AND; group rules OR among themselves and then
        AND with the globals. If a model has *any* group-scoped rule but none match the
        caller's groups, the caller has no grant → access is denied.
        """
        perm_col = f"perm_{operation}"
        async with env.dml_conn() as conn:
            gids_rows = await conn.execute(
                text("SELECT group_id FROM res_users_groups_rel WHERE user_id = :uid"),
                {"uid": uid},
            )
            group_ids = [row[0] for row in gids_rows]

            rows = await conn.execute(
                text(
                    f"SELECT r.id, r.domain_filter, r.global_rule, "
                    f"       EXISTS (SELECT 1 FROM ir_rule_group_rel g "
                    f"               WHERE g.rule_id = r.id "
                    f"               AND g.group_id = ANY(:gids)) AS matches "
                    f"FROM ir_rule r JOIN ir_model m ON m.id = r.model_id "
                    f"WHERE m.name = :model AND r.{perm_col} = TRUE"
                ),
                {"model": model_name, "gids": group_ids or [0]},
            )

            global_domains: list[list] = []
            group_domains: list[list] = []
            has_group_rule = False
            for row in rows:
                if not row[2]:  # not a global rule → it's a group rule
                    has_group_rule = True
                try:
                    dom = json.loads(row[1])
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(dom, list):
                    continue
                if row[2]:
                    global_domains.append(dom)
                elif row[3]:  # group rule that matches one of the caller's groups
                    group_domains.append(dom)
        return global_domains, group_domains, has_group_rule

    @staticmethod
    async def get_merged_domain(
        env: Environment,
        model_name: str,
        uid: int,
        operation: str,
    ) -> list | None:
        try:
            globals_, groups_, has_group_rule = await AccessEnforcer._fetch_rules(
                env, model_name, uid, operation
            )
        except Exception:
            _log.exception(
                "ir.rule lookup failed for %s/%s; applying no extra domain",
                model_name,
                operation,
            )
            return None

        parts: list[list] = list(globals_)

        if has_group_rule:
            if not groups_:
                return [["id", "=", 0]]  # model is group-gated and caller has no grant
            parts.append(_or_join(groups_))

        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        merged: list = []
        for _ in range(len(parts) - 1):
            merged.append("&")
        for p in parts:
            merged.extend(p)
        return merged

    @staticmethod
    async def check_access(
        env: Environment,
        model_name: str,
        uid: int,
        operation: str,
    ) -> None:
        """Raise ``AccessError`` when the caller is fully denied the operation on the model."""
        merged = await AccessEnforcer.get_merged_domain(env, model_name, uid, operation)
        if merged == [["id", "=", 0]]:
            raise AccessError(
                f"Access denied: operation '{operation}' on model '{model_name}' is restricted"
            )
