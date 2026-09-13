from dodoo.addons.analytic import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.analytic.data.seed import seed_analytic_data

    await seed_analytic_data(env)
