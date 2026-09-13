"""Registry of ``ir.rule`` record rules for the Inventory (`stock`) addon.

Rule spec shape (see ``dodoo.addons.stock.security.seed_rules``):
``{name, model, domain, groups: list[str] | None, perms: str}``.

``$company_ids``/``$uid`` in a domain are substituted by ``AccessEnforcer`` at query time.
Dotted-path leaves (e.g. ``location_id.warehouse_id.company_id``) are compiled to a relational
subquery by the ADR-028 domain engine.
"""

from __future__ import annotations

from typing import Any

from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER, seed_rules

STOCK_RULES: list[dict[str, Any]] = []


def manager_full(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: Inventory Manager full (company scope)",
        "model": model,
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_MANAGER],
        "perms": "rwck",
    }


def manager_full_dotted(model: str, path: str) -> dict[str, Any]:
    """Like :func:`manager_full` but scoped via a dotted-path relation to `company_id`."""
    return {
        "name": f"{model}: Inventory Manager full (company scope via {path})",
        "model": model,
        "domain": [[path, "in", "$company_ids"]],
        "groups": [GROUP_MANAGER],
        "perms": "rwck",
    }


def user_or_manager_operate(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: Inventory User/Manager operate (company scope)",
        "model": model,
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_USER, GROUP_MANAGER],
        "perms": "rwck",
    }


def user_or_manager_operate_dotted(model: str, path: str) -> dict[str, Any]:
    return {
        "name": f"{model}: Inventory User/Manager operate (company scope via {path})",
        "model": model,
        "domain": [[path, "in", "$company_ids"]],
        "groups": [GROUP_USER, GROUP_MANAGER],
        "perms": "rwck",
    }


def catalog_read(model: str) -> dict[str, Any]:
    """A nullable-``company_id`` config catalog: readable when global or in scope."""
    return {
        "name": f"{model}: catalog read (shared or in scope)",
        "model": model,
        "domain": ["|", ["company_id", "=", None], ["company_id", "in", "$company_ids"]],
        "groups": [GROUP_USER, GROUP_MANAGER],
        "perms": "r",
    }


def catalog_admin_write(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: catalog write (Inventory Manager)",
        "model": model,
        "domain": [[1, "=", 1]],
        "groups": [GROUP_MANAGER],
        "perms": "wck",
    }


def valuation_manager_read(model: str) -> dict[str, Any]:
    return {
        "name": f"{model}: valuation read (Inventory Manager, company scope)",
        "model": model,
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_MANAGER],
        "perms": "r",
    }


# --------------------------------------------------------------------------- US1 (catalog)
STOCK_RULES.extend(
    [
        catalog_read("product.category"),
        catalog_admin_write("product.category"),
        catalog_read("uom.category"),
        catalog_admin_write("uom.category"),
        catalog_read("uom.uom"),
        catalog_admin_write("uom.uom"),
        catalog_read("product.template"),
        catalog_admin_write("product.template"),
        catalog_read("product.product"),
        catalog_admin_write("product.product"),
    ]
)

# --------------------------------------------------------------------------- US2 (warehouses)
STOCK_RULES.extend(
    [
        manager_full("stock.warehouse"),
        manager_full("stock.location"),
        manager_full_dotted("stock.picking.type", "warehouse_id.company_id"),
    ]
)

# --------------------------------------------------------------------------- US3 (transfers)
STOCK_RULES.extend(
    [
        user_or_manager_operate_dotted("stock.picking", "picking_type_id.warehouse_id.company_id"),
        user_or_manager_operate_dotted("stock.move", "location_src_id.warehouse_id.company_id"),
        {
            "name": "stock.move.line: Inventory User/Manager operate",
            "model": "stock.move.line",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_USER, GROUP_MANAGER],
            "perms": "rwck",
        },
        {
            "name": "stock.quant: Inventory User/Manager operate",
            "model": "stock.quant",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_USER, GROUP_MANAGER],
            "perms": "rwck",
        },
    ]
)

# --------------------------------------------------------------------------- US4 (physical inventory)
STOCK_RULES.extend(
    [
        user_or_manager_operate_dotted(
            "stock.inventory.adjustment.log", "location_id.warehouse_id.company_id"
        ),
    ]
)

# --------------------------------------------------------------------------- US5 (lots/packages)
STOCK_RULES.extend(
    [
        user_or_manager_operate("stock.lot"),
        {
            "name": "stock.quant.package: Inventory User/Manager operate",
            "model": "stock.quant.package",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_USER, GROUP_MANAGER],
            "perms": "rwck",
        },
    ]
)

# --------------------------------------------------------------------------- US6 (routes)
STOCK_RULES.extend(
    [
        {
            "name": "stock.storage.category: Inventory Manager full",
            "model": "stock.storage.category",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_MANAGER],
            "perms": "rwck",
        },
        {
            "name": "stock.putaway.rule: Inventory Manager full",
            "model": "stock.putaway.rule",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_MANAGER],
            "perms": "rwck",
        },
        {
            "name": "stock.route: Inventory Manager full",
            "model": "stock.route",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_MANAGER],
            "perms": "rwck",
        },
        {
            "name": "stock.rule: Inventory Manager full",
            "model": "stock.rule",
            "domain": [[1, "=", 1]],
            "groups": [GROUP_MANAGER],
            "perms": "rwck",
        },
        manager_full_dotted("stock.warehouse.orderpoint", "location_id.warehouse_id.company_id"),
    ]
)

# --------------------------------------------------------------------------- US7 (scrap)
STOCK_RULES.extend(
    [
        user_or_manager_operate_dotted("stock.scrap", "location_src_id.warehouse_id.company_id"),
    ]
)


async def apply(env: Any) -> None:
    await seed_rules(env, STOCK_RULES)
