from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from dodoo.core.exceptions import AuthenticationError

_log = logging.getLogger(__name__)


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
