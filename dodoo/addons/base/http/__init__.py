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
