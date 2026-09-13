"""Product catalog addon.

Reproduces the behaviour of the Odoo 19.0 `product` and `uom` addons: categories, units of
measure, templates, attributes, and variants. Carries no dependency on `stock` or `account` — the
`stock` addon extends `product.product` with a `tracking` column and `stock_account` extends
`product.category`/`product.product` with valuation columns, both via additive `ALTER TABLE`
(see dodoo/addons/stock/data/product_product_ext.py and
dodoo/addons/stock_account/data/product_category_ext.py).
"""

from dodoo.addons.product import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.product.data.seed import seed_product_data

    await seed_product_data(env)
