"""``res.config.settings`` — RPC facade for the Settings screen (ADR-010).

Called via ``execute_kw``. Because ``_object_execute_kw`` injects ``uid`` only for
``search`` / ``search_read``, these methods read the caller through
``dodoo.core.context.get_uid()`` (populated by ``LanguageMiddleware`` from the validated
session token).

Modelled on Odoo's transient settings model. dodoo's installer does not register
``_abstract`` models, so this is a concrete model with a vestigial ``id``-only table that
is never populated — the methods are stateless.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.localization.i18n import translate
from dodoo.addons.localization.service import apply_country_localization
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


def _invalidate_company_lang_cache() -> None:
    try:
        from dodoo.http.middleware import invalidate_company_lang_cache

        invalidate_company_lang_cache()
    except Exception:
        pass


class ResConfigSettings(BaseModel):
    _name = "res.config.settings"

    # ------------------------------------------------------------------ helpers
    @classmethod
    async def is_admin(cls, env: Environment, uid: int | None) -> bool:
        if not uid:
            return False
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT 1 FROM res_users_groups_rel r "
                    "JOIN res_groups g ON g.id = r.group_id "
                    "WHERE r.user_id = :uid AND g.name = 'Administrator' LIMIT 1"
                ),
                {"uid": uid},
            )
            return row.fetchone() is not None

    @classmethod
    async def _company(cls, env: Environment) -> dict[str, Any]:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT id, lang, country_id, tax_label, tax_rounding_method, "
                    "       default_sale_tax_id, default_purchase_tax_id, "
                    "       default_fiscal_position_id, write_date "
                    "FROM res_company ORDER BY id LIMIT 1"
                )
            )
            return dict(row.mappings().one())

    @classmethod
    async def _country_code(cls, env: Environment, country_id: int | None) -> str | None:
        if not country_id:
            return None
        async with env.dml_conn() as conn:
            r = await conn.execute(
                text("SELECT code FROM res_country WHERE id = :id"), {"id": country_id}
            )
            row = r.fetchone()
            return row[0] if row else None

    @classmethod
    async def _effective_lang(cls, env: Environment, uid: int | None) -> str:
        async with env.dml_conn() as conn:
            personal = None
            if uid:
                r = await conn.execute(
                    text("SELECT lang FROM res_users WHERE id = :uid"), {"uid": uid}
                )
                row = r.fetchone()
                personal = row[0] if row else None
            if personal:
                active = await conn.execute(
                    text("SELECT 1 FROM res_lang WHERE code = :c AND active = TRUE"),
                    {"c": personal},
                )
                if active.fetchone():
                    return personal
            r = await conn.execute(text("SELECT lang FROM res_company ORDER BY id LIMIT 1"))
            row = r.fetchone()
            return row[0] if row and row[0] else "ar"

    @classmethod
    async def _lang_direction(cls, env: Environment, code: str) -> str:
        async with env.dml_conn() as conn:
            r = await conn.execute(
                text("SELECT direction FROM res_lang WHERE code = :c"), {"c": code}
            )
            row = r.fetchone()
            return row[0] if row and row[0] else "ltr"

    @classmethod
    async def _assert_active_lang(cls, env: Environment, code: str) -> None:
        async with env.dml_conn() as conn:
            r = await conn.execute(
                text("SELECT 1 FROM res_lang WHERE code = :c AND active = TRUE"),
                {"c": code},
            )
            if r.fetchone() is None:
                raise DodooError(f"Unknown or inactive language: {code!r}")

    @classmethod
    async def _assert_active_country(cls, env: Environment, code: str) -> None:
        async with env.dml_conn() as conn:
            r = await conn.execute(
                text("SELECT 1 FROM res_country WHERE code = :c AND active = TRUE"),
                {"c": code},
            )
            if r.fetchone() is None:
                raise DodooError(f"Unknown or inactive country: {code!r}")

    # ------------------------------------------------------------------ reads
    @classmethod
    async def get_values(cls, env: Environment) -> dict[str, Any]:
        company = await cls._company(env)
        country_code = await cls._country_code(env, company["country_id"])
        async with env.dml_conn() as conn:
            langs = await conn.execute(
                text(
                    "SELECT code, name, direction FROM res_lang "
                    "WHERE active = TRUE ORDER BY code"
                )
            )
            available_langs = [dict(m) for m in langs.mappings().all()]
            countries = await conn.execute(
                text(
                    "SELECT id, code, name, currency_code FROM res_country "
                    "WHERE active = TRUE ORDER BY name"
                )
            )
            available_countries = [dict(m) for m in countries.mappings().all()]

        wd = company["write_date"]
        return {
            "lang": company["lang"],
            "country_id": company["country_id"],
            "country_code": country_code,
            "tax_label": company["tax_label"],
            "tax_rounding_method": company["tax_rounding_method"],
            "default_sale_tax_id": company["default_sale_tax_id"],
            "default_purchase_tax_id": company["default_purchase_tax_id"],
            "default_fiscal_position_id": company["default_fiscal_position_id"],
            "company_write_date": wd.isoformat() if wd is not None else None,
            "available_langs": available_langs,
            "available_countries": available_countries,
        }

    # ------------------------------------------------------------------ writes
    @classmethod
    async def set_values(cls, env: Environment, vals: dict[str, Any]) -> dict[str, Any]:
        uid = get_uid()
        if not await cls.is_admin(env, uid):
            raise AccessError("Administrator privileges required to change settings")

        vals = vals or {}
        new_lang = vals.get("lang")
        new_country = (vals.get("country_code") or "").upper() or None
        confirm = bool(vals.get("confirm_currency_change", False))

        if new_lang:
            await cls._assert_active_lang(env, new_lang)
        if new_country:
            await cls._assert_active_country(env, new_country)

        company = await cls._company(env)
        company_id = company["id"]
        current_country = await cls._country_code(env, company["country_id"])

        # Optimistic concurrency (FR-033)
        current_wd = company["write_date"]
        current_wd_s = current_wd.isoformat() if current_wd is not None else None
        if vals.get("company_write_date") != current_wd_s:
            raise DodooError("settings_stale")

        extra: dict[str, Any] = {}
        if new_lang:
            extra["lang"] = new_lang

        # Country change → the service applies the package AND the lang write in one
        # transaction; the declined-currency path returns a warning with zero writes.
        if new_country and new_country != current_country:
            result = await apply_country_localization(
                env,
                company_id,
                new_country,
                confirm_currency_change=confirm,
                extra_company_vals=extra,
            )
            if result.get("warning"):
                return {
                    "ok": False,
                    "warning": result["warning"],
                    "detail": {
                        "from": result.get("from"),
                        "to": result.get("to"),
                        "posted_lines": result.get("posted_lines"),
                    },
                    "settings": await cls.get_values(env),
                }
            _invalidate_company_lang_cache()
            return {"ok": True, "applied": result, "settings": await cls.get_values(env)}

        # Language-only change (or no-op)
        if extra:
            async with env.dml_conn() as conn:
                assignments = ", ".join(f"{k} = :{k}" for k in extra)
                await conn.execute(
                    text(
                        f"UPDATE res_company SET {assignments}, write_date = now() "
                        "WHERE id = :cid"
                    ),
                    {**extra, "cid": company_id},
                )
                await conn.commit()
            _invalidate_company_lang_cache()

        return {"ok": True, "settings": await cls.get_values(env)}

    @classmethod
    async def set_user_lang(cls, env: Environment, lang: str | None) -> dict[str, Any]:
        uid = get_uid()
        if not uid:
            raise AccessError("Authentication required")

        code = (lang or "").strip()
        if code:
            await cls._assert_active_lang(env, code)

        async with env.dml_conn() as conn:
            await conn.execute(
                text(
                    "UPDATE res_users SET lang = :lang, write_date = now() WHERE id = :uid"
                ),
                {"lang": code or None, "uid": uid},
            )
            await conn.commit()

        effective = await cls._effective_lang(env, uid)
        return {
            "ok": True,
            "lang": code or None,
            "effective_lang": effective,
            "direction": await cls._lang_direction(env, effective),
            "label": translate("My language", effective),
        }
