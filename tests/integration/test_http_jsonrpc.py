from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dodoo.http.app import create_app
from dodoo.http.routing import RouteRegistry


@pytest_asyncio.fixture(scope="module")
async def app_client(env):
    # Register test-only route in conftest fixture (not in any production module)
    from fastapi.responses import JSONResponse

    async def _ping_handler(request):
        return JSONResponse({"pong": True})

    RouteRegistry.get().add_route("/test/ping", ["GET"], _ping_handler, auth="public")

    app = create_app(env)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    RouteRegistry.get().remove_route("/test/ping", ["GET"])


def _rpc(service: str, method: str, args=None, kwargs=None, id_=1):
    return {
        "jsonrpc": "2.0",
        "method": "call",
        "id": id_,
        "params": {
            "service": service,
            "method": method,
            "args": args or [],
            "kwargs": kwargs or {},
        },
    }


async def test_version_returns_result(app_client):
    resp = await app_client.post("/jsonrpc", json=_rpc("common", "version"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert "server_version" in data["result"]


async def test_missing_method_returns_32600(app_client):
    # Omit "method" key — envelope is invalid
    resp = await app_client.post("/jsonrpc", json={"jsonrpc": "2.0", "id": 2, "params": {}})
    data = resp.json()
    assert data["error"]["code"] in (-32600, -32601)


async def test_unknown_service_returns_32601(app_client):
    resp = await app_client.post("/jsonrpc", json=_rpc("unknown_service", "do_thing"))
    data = resp.json()
    assert data["error"]["code"] == -32601


async def test_wrong_param_count_returns_32602(app_client):
    # authenticate with no args — will raise TypeError (< 2 args)
    resp = await app_client.post("/jsonrpc", json=_rpc("common", "authenticate", args=[]))
    data = resp.json()
    assert data["error"]["code"] in (-32602, -32000)


async def test_unauthenticated_object_returns_32000(app_client):
    resp = await app_client.post(
        "/jsonrpc",
        json=_rpc("object", "execute_kw", args=["res.users", "search", [[]]]),
        headers={"X-Session-Token": "invalid-token-xyz"},
    )
    data = resp.json()
    assert data["error"]["code"] == -32000
    assert data["error"]["data"]["type"] == "AuthenticationError"


async def test_test_ping_route_returns_200(app_client):
    resp = await app_client.get("/test/ping")
    assert resp.status_code == 200
    assert resp.json()["pong"] is True
