from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dodoo.http.app import create_app
from dodoo.http.routing import MountRegistry, RouteRegistry


@pytest_asyncio.fixture(scope="module")
async def web_client(env):
    import dodoo.addons.web.http  # noqa: F401 — registers /web/client route and StaticFiles mount

    app = create_app(env)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    RouteRegistry.get().remove_route("/web/client", ["GET"])
    MountRegistry.reset()


@pytest.mark.asyncio
async def test_web_client_returns_200(web_client):
    r = await web_client.get("/web/client")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert b"<!DOCTYPE html>" in r.content


@pytest.mark.asyncio
async def test_static_app_js_returns_200(web_client):
    r = await web_client.get("/web/static/app.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_static_style_css_returns_200(web_client):
    r = await web_client.get("/web/static/style.css")
    assert r.status_code == 200
    assert "css" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_static_login_js_returns_200(web_client):
    r = await web_client.get("/web/static/views/login.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
