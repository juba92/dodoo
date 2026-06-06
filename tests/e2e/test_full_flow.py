from __future__ import annotations

from httpx import ASGITransport, AsyncClient


async def test_library_mode_no_http_server(env):
    """SC-005 / FR-015: Environment usable as library without HTTP server."""
    from dodoo.addons.base.models.res_users import ResUsers

    ids = await ResUsers.search(env, [])
    assert isinstance(ids, list)


async def test_http_mode_full_flow(env):
    """Full end-to-end: authenticate → CRUD → logout → invalid token."""
    from dodoo.auth.session import SessionManager
    from dodoo.http.app import create_app
    from dodoo.http.routing import RouteRegistry

    RouteRegistry.reset()
    import dodoo.addons.base.http  # noqa: F401

    app = create_app(env)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Authenticate
        auth_resp = await client.post(
            "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
                "params": {
                    "service": "common",
                    "method": "authenticate",
                    "args": ["admin", "admin"],
                    "kwargs": {},
                },
            },
        )
        assert auth_resp.status_code == 200
        auth_data = auth_resp.json()
        assert "result" in auth_data
        token = auth_data["result"]["session_token"]
        uid = auth_data["result"]["uid"]
        assert isinstance(token, str) and len(token) > 10
        assert isinstance(uid, int) and uid > 0

        # CRUD: create a group
        create_resp = await client.post(
            "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "id": 2,
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [
                        "res.groups",
                        "create",
                        [{"name": "E2E Group", "full_name": "E2E / Test"}],
                    ],
                    "kwargs": {},
                },
            },
            headers={"X-Session-Token": token},
        )
        create_data = create_resp.json()
        assert "result" in create_data
        group_id = create_data["result"]
        assert isinstance(group_id, int)

        # Search it back
        search_resp = await client.post(
            "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "id": 3,
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": ["res.groups", "search_read", [[["name", "=", "E2E Group"]]]],
                    "kwargs": {"fields": ["name", "full_name"]},
                },
            },
            headers={"X-Session-Token": token},
        )
        search_data = search_resp.json()
        assert "result" in search_data
        results = search_data["result"]
        assert len(results) >= 1
        assert results[0]["name"] == "E2E Group"

        # Logout
        await SessionManager.invalidate(env, token)

        # Verify invalidated token rejected
        invalid_resp = await client.post(
            "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "id": 4,
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": ["res.groups", "search", [[]]],
                    "kwargs": {},
                },
            },
            headers={"X-Session-Token": token},
        )
        invalid_data = invalid_resp.json()
        assert invalid_data["error"]["code"] == -32000
        assert invalid_data["error"]["data"]["type"] == "AuthenticationError"
