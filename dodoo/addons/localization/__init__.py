"""Localization & Settings addon.

Installs two UI languages (Arabic default, English), country + state reference data,
and a country-driven localization service that seeds currency / taxes / fiscal positions
into the existing ``account`` models. Two translation paths reach the web client:

* the server runs model field labels / model names through the in-memory catalog in
  ``i18n.py`` (via ``BaseModel.fields_get`` reading the request language context), and
* ``GET /web/i18n/{lang}.json`` serves the client-string catalog + locale metadata that
  the SPA loads at bootstrap.

The only concrete localization package is Egypt (``packs/egypt.py``); every other seeded
country (including the neutral United Kingdom) has no package.
"""

from dodoo.addons.localization import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.localization.data.seed import seed_localization_data

    await seed_localization_data(env)
