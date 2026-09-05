from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from dodoo.core.context import set_lang, set_uid
from dodoo.core.exceptions import AuthenticationError

_log = logging.getLogger(__name__)

# Cache the single company's system-default language so the per-request resolution is a
# dict/attr lookup plus (only when a session token is present) one indexed res_users read.
_company_lang_cache: dict[str, str | None] = {"value": None}


def invalidate_company_lang_cache() -> None:
    _company_lang_cache["value"] = None


async def _stub_validator(token: str, env: Any) -> int:
    raise AuthenticationError("Authentication service not yet initialised")


async def _real_validator(token: str, env: Any) -> int:
    from dodoo.auth.session import SessionManager

    return await SessionManager.validate(env, token)


# Module-level variable — wired to real async validator (T057)
session_validator: Callable[[str, Any], Awaitable[int]] = _real_validator


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        old_factory = logging.getLogRecordFactory()

        def _factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            record.correlation_id = correlation_id  # type: ignore[attr-defined]
            return record

        logging.setLogRecordFactory(_factory)
        try:
            response = await call_next(request)
        finally:
            logging.setLogRecordFactory(old_factory)

        response.headers["X-Correlation-ID"] = correlation_id
        return response


class LanguageMiddleware(BaseHTTPMiddleware):
    """Resolve the caller (uid) and effective UI language once per request.

    Effective language = personal ``res_users.lang`` (if a valid, active code) → the
    company's ``res_company.lang`` → ``"ar"`` (seed default). Both values are stashed in
    context vars (:mod:`dodoo.core.context`) for the ORM / settings model to read. Inert
    when the localization tables are absent (``res_lang`` not installed).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        set_uid(None)
        set_lang("en")
        env = getattr(request.app.state, "env", None)
        if env is not None:
            try:
                await self._resolve(request, env)
            except Exception:  # never let language resolution break a request
                _log.debug("language resolution skipped", exc_info=True)
        return await call_next(request)

    async def _resolve(self, request: Request, env: Any) -> None:
        token = request.headers.get("X-Session-Token", "")
        uid: int | None = None
        if token:
            try:
                uid = await session_validator(token, env)
            except AuthenticationError:
                uid = None
        set_uid(uid)

        if _company_lang_cache["value"] is None:
            async with env.dml_conn() as conn:
                row = await conn.execute(
                    text("SELECT lang FROM res_company ORDER BY id LIMIT 1")
                )
                r = row.fetchone()
                _company_lang_cache["value"] = (r[0] if r and r[0] else "ar")
        effective = _company_lang_cache["value"] or "ar"

        if uid is not None:
            async with env.dml_conn() as conn:
                row = await conn.execute(
                    text("SELECT lang FROM res_users WHERE id = :uid"), {"uid": uid}
                )
                r = row.fetchone()
                personal = r[0] if r and r[0] else None
                if personal and personal != effective:
                    active = await conn.execute(
                        text(
                            "SELECT 1 FROM res_lang WHERE code = :c AND active = TRUE"
                        ),
                        {"c": personal},
                    )
                    if active.fetchone():
                        effective = personal
                    else:
                        _log.info(
                            "user %s has inactive lang %r; falling back to %r",
                            uid,
                            personal,
                            effective,
                        )
        set_lang(effective)
