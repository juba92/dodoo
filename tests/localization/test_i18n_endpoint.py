"""Integration tests for the /web/i18n endpoint and translated fields_get."""
from __future__ import annotations

import time

import httpx
import pytest
import pytest_asyncio

from dodoo.http.app import create_app
from dodoo.http.routing import RouteRegistry


@pytest_asyncio.fixture
async def client(env):
    """ASGI client with all addon REST routes registered against a fresh registry.

    The shared ``env`` fixture calls ``RouteRegistry.reset()``; addon route decorators
    run only once at import, so we reload the http modules to re-register them here.
    """
    import importlib

    from dodoo.http.routing import MountRegistry

    RouteRegistry.reset()
    MountRegistry.reset()

    import dodoo.addons.account.http as acc_http
    import dodoo.addons.base.http as base_http
    import dodoo.addons.localization.http as loc_http
    import dodoo.addons.web.http as web_http

    for m in (base_http, web_http, acc_http, loc_http):
        importlib.reload(m)

    app = create_app(env)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_ar_catalog_is_rtl_with_terms(client):
    r = await client.get("/web/i18n/ar.json")
    assert r.status_code == 200
    body = r.json()
    assert body["direction"] == "rtl"
    assert body["lang"] == "ar"
    assert body["terms"].get("Home") == "الرئيسية"
    assert isinstance(body["grouping"], list)


async def test_en_catalog_is_ltr(client):
    r = await client.get("/web/i18n/en.json")
    assert r.status_code == 200
    assert r.json()["direction"] == "ltr"


async def test_unknown_language_returns_400(client):
    r = await client.get("/web/i18n/fr.json")
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_language"


async def test_core_info_exposes_lang_direction_admin(client):
    r = await client.get("/web/core/info")
    body = r.json()
    assert body["lang"] == "ar"
    assert body["direction"] == "rtl"
    assert body["is_admin"] is False


async def test_language_resolution_overhead_under_50ms(client, env):
    """PERF-001: translated fields_get adds < 50 ms mean vs. an untranslated baseline."""
    from dodoo.addons.base.models.res_users import ResUsers
    from dodoo.core.context import set_lang

    n = 50
    set_lang("en")  # 'en' catalog: identity — approximates the untranslated cost
    t0 = time.monotonic()
    for _ in range(n):
        await ResUsers.fields_get(env)
    baseline = (time.monotonic() - t0) / n

    set_lang("ar")
    t0 = time.monotonic()
    for _ in range(n):
        await ResUsers.fields_get(env)
    translated = (time.monotonic() - t0) / n

    assert (translated - baseline) < 0.050, (baseline, translated)


@pytest.mark.parametrize("lang,expect", [("ar", "الإعدادات"), ("en", "Settings")])
async def test_fields_get_label_translation_hook(env, lang, expect):
    """The core fields_get hook runs a known label through the catalog for the active lang."""
    from dodoo.core.context import set_lang

    # 'Settings' is not a res.users field label, so assert on the helper the hook uses.
    from dodoo.core.models import _translate_label

    set_lang(lang)
    assert _translate_label("Settings") == expect
