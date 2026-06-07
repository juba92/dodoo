from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.responses import JSONResponse

from dodoo.core.exceptions import (
    AccessError,
    AuthenticationError,
    DodooError,
    DomainError,
)

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "1"


def _jsonify(obj: Any) -> Any:
    """Recursively coerce non-JSON-serializable objects to JSON-safe primitives."""
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


def _ok(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": _jsonify(result)}


def _err(id_: Any, code: int, message: str, exc_type: str = "") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": code, "message": message, "data": {"type": exc_type}},
    }


async def jsonrpc_handler(request: Request) -> JSONResponse:
    env: Environment = request.app.state.env

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_err(None, -32700, "Parse error", "ParseError"))

    # Validate JSON-RPC 2.0 envelope
    if not isinstance(body, dict):
        return JSONResponse(_err(None, -32600, "Invalid request", "InvalidRequest"))

    req_id = body.get("id")
    jsonrpc = body.get("jsonrpc")
    method = body.get("method")
    params = body.get("params", {})

    if jsonrpc != "2.0" or method is None or not isinstance(params, dict):
        return JSONResponse(_err(req_id, -32600, "Invalid request", "InvalidRequest"))

    service = params.get("service", "")
    svc_method = params.get("method", "")
    args = params.get("args", [])
    kwargs = params.get("kwargs", {})

    # Resolve handler
    dispatch_key = (service, svc_method)
    handler = _DISPATCH.get(dispatch_key)
    if handler is None:
        return JSONResponse(_err(req_id, -32601, "Method not found", "MethodNotFound"))

    # Session auth for object service
    uid: int | None = None
    if service == "object":
        token = request.headers.get("X-Session-Token", "")
        try:
            import dodoo.http.middleware as _mw

            uid = await _mw.session_validator(token, env)
        except AuthenticationError as exc:
            return JSONResponse(_err(req_id, -32000, str(exc), "AuthenticationError"))

    try:
        result = await handler(env, uid, args, kwargs)
        return JSONResponse(_ok(req_id, result))
    except AuthenticationError as exc:
        return JSONResponse(_err(req_id, -32000, str(exc), "AuthenticationError"))
    except AccessError as exc:
        return JSONResponse(_err(req_id, -32000, str(exc), "AccessError"))
    except DomainError as exc:
        return JSONResponse(_err(req_id, -32602, str(exc), "DomainError"))
    except DodooError as exc:
        return JSONResponse(_err(req_id, -32602, str(exc), "DodooError"))
    except TypeError as exc:
        return JSONResponse(
            _err(req_id, -32602, f"Invalid params: {exc}", "InvalidParams")
        )
    except Exception as exc:
        _log.exception("Internal error in JSON-RPC handler")
        return JSONResponse(_err(req_id, -32603, "Internal error", type(exc).__name__))


# ---- Service method handlers ----


async def _common_version(env: Any, uid: Any, args: list, kwargs: dict) -> dict:
    return {"server_version": SERVER_VERSION, "protocol_version": PROTOCOL_VERSION}


async def _common_authenticate(env: Any, uid: Any, args: list, kwargs: dict) -> dict:
    if len(args) < 2:
        raise TypeError("authenticate requires [login, password]")
    login, password = args[0], args[1]
    from dodoo.auth.session import SessionManager

    token = await SessionManager.authenticate(env, login, password)
    uid_val = await SessionManager.validate(env, token)
    return {"uid": uid_val, "session_token": token}


async def _common_logout(env: Any, uid: Any, args: list, kwargs: dict) -> bool:
    # Token comes from header; handled by caller; stub returns True
    return True


async def _object_execute_kw(env: Any, uid: Any, args: list, kwargs: dict) -> Any:
    if len(args) < 3:
        raise TypeError("execute_kw requires [model, method, args, kwargs]")
    model_name: str = args[0]
    method_name: str = args[1]
    method_args: list = args[2] if len(args) > 2 else []
    method_kwargs: dict = args[3] if len(args) > 3 else kwargs

    if method_name.startswith("_"):
        raise AccessError(
            f"Method '{method_name}' is private and cannot be called via JSON-RPC"
        )

    model_proxy = env[model_name]
    method = getattr(model_proxy, method_name, None)
    if method is None:
        from dodoo.core.exceptions import DodooError

        raise DodooError(f"Model '{model_name}' has no method '{method_name}'")

    # Inject uid into search/search_read
    if method_name in ("search", "search_read") and uid is not None:
        method_kwargs = {**method_kwargs, "uid": uid}

    return await method(*method_args, **method_kwargs)


_DISPATCH: dict[tuple[str, str], Any] = {
    ("common", "version"): _common_version,
    ("common", "authenticate"): _common_authenticate,
    ("common", "logout"): _common_logout,
    ("object", "execute_kw"): _object_execute_kw,
}
