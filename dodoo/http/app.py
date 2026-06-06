from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dodoo.http.jsonrpc import jsonrpc_handler
from dodoo.http.middleware import CorrelationMiddleware
from dodoo.http.routing import RouteRegistry

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


def create_app(env: Environment) -> FastAPI:
    app = FastAPI(title="Dodoo ERP", version="0.1.0")
    app.state.env = env

    # CORS: localhost only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_origin_regex=r"http://127\.0\.0\.1(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(CorrelationMiddleware)

    # JSON-RPC endpoint
    app.add_api_route("/jsonrpc", jsonrpc_handler, methods=["POST"])

    # Register module REST routes
    RouteRegistry.get().register_with_app(app)

    @app.on_event("startup")
    async def _startup() -> None:
        _log.info("dodoo.http started")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await env.close()
        _log.info("dodoo.http stopped")

    return app
