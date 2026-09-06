"""Registry of ``ir.rule`` record rules for the HR addon.

Each user story appends its rule specs to :data:`HR_RULES` (imported for side effect from the
per-area data modules). :func:`apply` seeds them all after ``sync_ir_model`` has run.

Rule spec shape (see ``dodoo.addons.hr.security.seed_rules``):
``{name, model, domain, groups: list[str] | None, perms: str}``.

``uid`` in a domain is substituted by ``AccessEnforcer`` at query time. Company scope is a single
company today, so ``["company_id", "=", <n>]`` style domains use the ``ANY``-friendly
``["company_id", "in", ...]`` form where a list is expected; the enforcer resolves ``uid``.
"""

from __future__ import annotations

from typing import Any

from dodoo.addons.hr.security import (
    GROUP_ADMIN,
    GROUP_EMPLOYEE,
    GROUP_OFFICER,
    seed_rules,
)

HR_RULES: list[dict[str, Any]] = []

# Deny-by-default helper: a model with sensitive data must have at least one rule for
# *every* path, else an un-grouped user reads it freely (AccessEnforcer returns None when a
# model has no applicable rule). Callers add `deny_all("hr.contract")` for such models.


def deny_all(model: str) -> None:
    """No-op. With the Odoo rule semantics in ``AccessEnforcer.get_merged_domain`` a
    model that has *any* group-scoped rule automatically denies a caller who is in none
    of those groups — an explicit global deny rule is unnecessary (and would also
    AND-deny the grouped users). Kept as a call so the intent stays visible in the
    per-area rule lists; ``seed_rules`` skips ``None`` entries."""
    return None


def officer_full(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: HR Officer/Administrator full (company scope)",
        "model": model,
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_OFFICER, GROUP_ADMIN],
        "perms": "rwck",
    }


def catalog_read(model: str) -> dict[str, Any]:
    """A nullable-``company_id`` config catalog: readable when global or in scope."""
    return {
        "name": f"{model}: catalog read (shared or in scope)",
        "model": model,
        "domain": ["|", ["company_id", "=", None], ["company_id", "in", "$company_ids"]],
        "groups": [GROUP_EMPLOYEE, GROUP_OFFICER, GROUP_ADMIN],
        "perms": "r",
    }


def catalog_admin_write(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: catalog write (Administrator)",
        "model": model,
        "domain": [[1, "=", 1]],
        "groups": [GROUP_ADMIN],
        "perms": "wck",
    }


async def apply(env: Any) -> None:
    await seed_rules(env, HR_RULES)
