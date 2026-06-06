from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from dodoo.auth.session import SessionManager
from dodoo.core.exceptions import AuthenticationError
from dodoo.core.fields import Char
from dodoo.core.migration import MigrationRunner
from dodoo.core.models import BaseModel


class RestrictedModel(BaseModel):
    _name = "restricted.model"
    secret = Char(size=256)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_auth_tables(env):
    from dodoo.addons.base.models import (
        IrModel,
        IrModelField,
        IrModule,
        IrRule,
        IrSession,
        ResGroups,
        ResUsers,
    )

    runner = MigrationRunner(env._ddl_engine)
    for cls in [
        IrModule,
        IrModel,
        IrModelField,
        ResGroups,
        ResUsers,
        IrSession,
        IrRule,
        RestrictedModel,
    ]:
        try:
            env.registry.register(cls)
        except Exception:
            pass
        await runner.install(cls)

    # Create junction tables
    async with env._ddl_engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS res_users_groups_rel ("
                "user_id INTEGER NOT NULL REFERENCES res_users(id) ON DELETE CASCADE, "
                "group_id INTEGER NOT NULL REFERENCES res_groups(id) ON DELETE CASCADE, "
                "PRIMARY KEY (user_id, group_id))"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ir_rule_group_rel ("
                "rule_id INTEGER NOT NULL REFERENCES ir_rule(id) ON DELETE CASCADE, "
                "group_id INTEGER NOT NULL REFERENCES res_groups(id) ON DELETE CASCADE, "
                "PRIMARY KEY (rule_id, group_id))"
            )
        )

    from dodoo.addons.base.data.base_data import seed_base_data

    await seed_base_data(env)


async def test_authenticate_returns_token(env):
    token = await SessionManager.authenticate(env, "admin", "admin")
    assert isinstance(token, str) and len(token) > 20


async def test_valid_token_validates(env):
    token = await SessionManager.authenticate(env, "admin", "admin")
    uid = await SessionManager.validate(env, token)
    assert isinstance(uid, int) and uid > 0


async def test_expired_token_raises(env):
    token = await SessionManager.authenticate(env, "admin", "admin")
    # Manually expire the token
    async with env.dml_conn() as conn:
        past = datetime.now(UTC) - timedelta(hours=1)
        await conn.execute(
            text("UPDATE ir_session SET expire_date = :past WHERE token = :tok"),
            {"past": past, "tok": token},
        )
        await conn.commit()

    with pytest.raises(AuthenticationError):
        await SessionManager.validate(env, token)


async def test_logout_invalidates_token(env):
    token = await SessionManager.authenticate(env, "admin", "admin")
    await SessionManager.invalidate(env, token)
    with pytest.raises(AuthenticationError):
        await SessionManager.validate(env, token)


async def test_reuse_invalidated_token_raises(env):
    token = await SessionManager.authenticate(env, "admin", "admin")
    await SessionManager.invalidate(env, token)
    with pytest.raises(AuthenticationError):
        await SessionManager.validate(env, token)


async def test_valid_token_accepted_by_object_service(env):
    from dodoo.http.app import create_app
    from dodoo.http.routing import RouteRegistry

    RouteRegistry.reset()
    # Re-register base routes
    import dodoo.addons.base.http  # noqa: F401

    app = create_app(env)
    token = await SessionManager.authenticate(env, "admin", "admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": ["res.users", "search", [[]]],
                    "kwargs": {},
                },
            },
            headers={"X-Session-Token": token},
        )
    data = resp.json()
    assert "result" in data or data.get("error", {}).get("code") != -32000
