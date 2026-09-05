"""Integration tests for res.config.settings (get/set values, admin guard, concurrency)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from dodoo.addons.localization.models.res_config_settings import ResConfigSettings
from dodoo.core.context import set_uid
from dodoo.core.exceptions import AccessError, DodooError


@pytest_asyncio.fixture(autouse=True)
async def _reset_system_lang(env):
    """Keep the system default at Arabic between tests (shared session DB)."""
    yield
    async with env.dml_conn() as conn:
        await conn.execute(text("UPDATE res_company SET lang = 'ar'"))
        await conn.execute(text("UPDATE res_users SET lang = NULL"))
        await conn.commit()


async def _non_admin_uid(env) -> int:
    async with env.dml_conn() as conn:
        r = await conn.execute(
            text("SELECT id FROM res_users WHERE login = 'plain_user'")
        )
        row = r.fetchone()
        if row:
            return row[0]
    from dodoo.addons.base.models.res_users import ResUsers

    return await ResUsers.create(
        env, {"login": "plain_user", "name": "Plain User", "active": True}
    )


async def test_get_values_shape(env, admin_uid):
    set_uid(admin_uid)
    v = await ResConfigSettings.get_values(env)
    assert v["lang"] == "ar"
    assert v["country_code"] == "EG"
    assert v["tax_label"] == "VAT"
    assert {"code", "name", "direction"} <= set(v["available_langs"][0])
    assert any(c["code"] == "GB" for c in v["available_countries"])
    assert v["company_write_date"]


async def test_set_values_language_happy_path(env, admin_uid):
    set_uid(admin_uid)
    v = await ResConfigSettings.get_values(env)
    res = await ResConfigSettings.set_values(
        env, {"lang": "en", "company_write_date": v["company_write_date"]}
    )
    assert res["ok"] is True
    assert (await ResConfigSettings.get_values(env))["lang"] == "en"


async def test_set_values_requires_admin(env):
    uid = await _non_admin_uid(env)
    set_uid(uid)
    v_uid_admin = None
    async with env.dml_conn() as conn:
        r = await conn.execute(text("SELECT id FROM res_users WHERE login='admin'"))
        v_uid_admin = r.scalar_one()
    set_uid(v_uid_admin)
    v = await ResConfigSettings.get_values(env)
    set_uid(uid)
    with pytest.raises(AccessError):
        await ResConfigSettings.set_values(
            env, {"lang": "en", "company_write_date": v["company_write_date"]}
        )


async def test_set_values_rejects_stale_write_date(env, admin_uid):
    set_uid(admin_uid)
    with pytest.raises(DodooError, match="settings_stale"):
        await ResConfigSettings.set_values(
            env, {"lang": "en", "company_write_date": "1999-01-01T00:00:00"}
        )
    assert (await ResConfigSettings.get_values(env))["lang"] == "ar"


async def test_set_values_rejects_unknown_language(env, admin_uid):
    set_uid(admin_uid)
    v = await ResConfigSettings.get_values(env)
    with pytest.raises(DodooError):
        await ResConfigSettings.set_values(
            env, {"lang": "zz", "company_write_date": v["company_write_date"]}
        )


# ── US2: personal language override ────────────────────────────────────────────
async def test_personal_lang_overrides_system_default(env, admin_uid):
    set_uid(admin_uid)
    res = await ResConfigSettings.set_user_lang(env, "en")
    assert res["ok"] is True
    assert res["effective_lang"] == "en"
    assert res["direction"] == "ltr"
    # system default is still Arabic for a preference-less user
    other = await _non_admin_uid(env)
    assert await ResConfigSettings._effective_lang(env, other) == "ar"


async def test_clearing_personal_lang_reverts_to_system_default(env, admin_uid):
    set_uid(admin_uid)
    await ResConfigSettings.set_user_lang(env, "en")
    res = await ResConfigSettings.set_user_lang(env, "")
    assert res["effective_lang"] == "ar"


async def test_new_user_without_lang_resolves_to_system_default(env, admin_uid):
    from dodoo.addons.base.models.res_users import ResUsers

    new_uid = await ResUsers.create(
        env, {"login": f"u{admin_uid}x", "name": "No Lang", "active": True}
    )
    assert await ResConfigSettings._effective_lang(env, new_uid) == "ar"


async def test_inactive_personal_lang_falls_back(env, admin_uid):
    async with env.dml_conn() as conn:
        await conn.execute(
            text("UPDATE res_users SET lang = 'zz' WHERE id = :u"), {"u": admin_uid}
        )
        await conn.commit()
    assert await ResConfigSettings._effective_lang(env, admin_uid) == "ar"
