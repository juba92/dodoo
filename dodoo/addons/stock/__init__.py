"""Inventory addon.

Reproduces the behaviour of the Odoo 19.0 `stock` addon: warehouses, locations, operation types,
transfers/stock moves, physical inventory, lots/serial numbers, packages, putaway rules, storage
categories, routes, reordering rules, and scrap. Depends on `product` + `base` + `web` +
`localization` — carries **no** dependency on `account`. Valuation is delivered separately in
`dodoo/addons/stock_account/`, which hooks `StockMove.action_set_state` at import time
(ADR-034) rather than `stock` calling into it.
"""

from dodoo.addons.stock import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.stock.data.seed import seed_stock_data

    await seed_stock_data(env)
