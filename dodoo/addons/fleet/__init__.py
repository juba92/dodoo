"""Fleet addon.

Reproduces the Odoo 19.0 ``fleet`` addon: vehicles with a seven-state lifecycle,
brands/models, employee drivers (history retained), odometer logs, leasing/insurance
contracts with expiry alerts, and service logs. Depends on ``hr`` only for the
``fleet.vehicle.driver_id -> hr.employee`` link. Amounts are plain ``Monetary`` values —
no accounting posting.
"""

from dodoo.addons.fleet import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.fleet.data.seed import seed_fleet_data

    await seed_fleet_data(env)
