from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from dodoo.http.routing import route

_log = logging.getLogger(__name__)


@route("/web/session/authenticate", methods=["POST"], auth="public")
async def authenticate(request: Request) -> JSONResponse:
    body = await request.json()
    login = body.get("login", "")
    password = body.get("password", "")
    env = request.app.state.env
    from dodoo.auth.session import SessionManager

    try:
        token = await SessionManager.authenticate(env, login, password)
        uid = await SessionManager.validate(env, token)
        return JSONResponse({"uid": uid, "session_token": token})
    except Exception:
        return JSONResponse({"error": "Authentication failed"}, status_code=401)


@route("/web/session/logout", methods=["POST"], auth="session")
async def logout(request: Request) -> JSONResponse:
    token = request.headers.get("X-Session-Token", "")
    env = request.app.state.env
    from dodoo.auth.session import SessionManager

    await SessionManager.invalidate(env, token)
    return JSONResponse({"result": "ok"})


@route("/web/health", methods=["GET"], auth="public")
async def health(request: Request) -> JSONResponse:
    env = request.app.state.env
    try:
        async with env.dml_conn() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "db": "connected"})
    except Exception:
        return JSONResponse({"status": "degraded", "db": "disconnected"}, status_code=503)


@route("/web/core/info", methods=["GET"], auth="public")
async def core_info(request: Request) -> JSONResponse:
    env = request.app.state.env
    from dodoo.core.context import get_lang, get_uid

    lang = get_lang()
    uid = get_uid()
    async with env.dml_conn() as conn:
        modules = await conn.execute(
            text("SELECT name, version, state FROM ir_module WHERE application = TRUE ORDER BY name")
        )
        users = await conn.execute(text("SELECT COUNT(*) FROM res_users"))
        groups = await conn.execute(text("SELECT COUNT(*) FROM res_groups"))

        direction = "ltr"
        is_admin = False
        try:
            drow = await conn.execute(
                text("SELECT direction FROM res_lang WHERE code = :c"), {"c": lang}
            )
            d = drow.fetchone()
            if d and d[0]:
                direction = d[0]
        except Exception:
            pass
        if uid:
            arow = await conn.execute(
                text(
                    "SELECT 1 FROM res_users_groups_rel r "
                    "JOIN res_groups g ON g.id = r.group_id "
                    "WHERE r.user_id = :uid AND g.name = 'Administrator' LIMIT 1"
                ),
                {"uid": uid},
            )
            is_admin = arow.fetchone() is not None

    models = sorted(env.registry._models.keys())
    return JSONResponse(
        {
            "modules": [
                {"name": r[0], "version": r[1], "state": r[2]} for r in modules.fetchall()
            ],
            "models": models,
            "users": users.scalar_one(),
            "groups": groups.scalar_one(),
            "lang": lang,
            "direction": direction,
            "is_admin": is_admin,
        }
    )
