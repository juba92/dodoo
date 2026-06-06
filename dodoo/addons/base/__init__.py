from dodoo.addons.base import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.base.data.base_data import seed_base_data

    await seed_base_data(env)
