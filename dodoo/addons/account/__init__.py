from dodoo.addons.account import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.account.data.account_data import seed_account_data

    await seed_account_data(env)
