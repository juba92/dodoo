from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from dodoo.core.db import create_ddl_engine, create_dml_engine, get_connection
from dodoo.core.registry import ModelRegistry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    from dodoo.core.models import BaseModel


class _ModelProxy:
    def __init__(self, model: type[BaseModel], env: Environment) -> None:
        self._model = model
        self._env = env

    async def create(self, vals: dict[str, Any]) -> int:
        return await self._model.create(self._env, vals)

    async def read(self, ids: list[int], fields: list[str] | None = None) -> list[dict[str, Any]]:
        return await self._model.read(self._env, ids, fields)

    async def write(self, ids: list[int], vals: dict[str, Any]) -> bool:
        return await self._model.write(self._env, ids, vals)

    async def unlink(self, ids: list[int]) -> bool:
        return await self._model.unlink(self._env, ids)

    async def search(
        self,
        domain: list | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
        uid: int | None = None,
    ) -> list[int]:
        return await self._model.search(self._env, domain, limit, offset, order, uid=uid)

    async def search_read(
        self,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
        uid: int | None = None,
    ) -> list[dict[str, Any]]:
        return await self._model.search_read(
            self._env, domain, fields, limit, offset, order, uid=uid
        )

    async def fields_get(self, attributes: list[str] | None = None) -> dict[str, dict[str, Any]]:
        return await self._model.fields_get(self._env, attributes)

    def __getattr__(self, name: str) -> Any:
        """Fall through to underlying model classmethod with env injected."""
        if name.startswith("_"):
            raise AttributeError(name)
        model_method = getattr(self._model, name, None)
        if model_method is None:
            raise AttributeError(f"'{self._model._name}' has no method '{name}'")
        import functools

        @functools.wraps(model_method)
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            return await model_method(self._env, *args, **kwargs)

        return _wrapper


class Environment:
    def __init__(
        self,
        dml_engine: AsyncEngine,
        ddl_engine: AsyncEngine,
        registry: ModelRegistry,
    ) -> None:
        self._dml_engine = dml_engine
        self._ddl_engine = ddl_engine
        self.registry = registry
        self.modules: _ModuleFacade | None = None

    @classmethod
    async def create(cls, database_url: str = "") -> Environment:
        if database_url:
            os.environ.setdefault("DATABASE_URL", database_url)
            os.environ.setdefault("DATABASE_MIGRATION_URL", database_url)

        dml_engine = create_dml_engine()
        ddl_engine = create_ddl_engine()
        registry = ModelRegistry()

        from dodoo.core.bootstrap import bootstrap

        async with ddl_engine.begin() as ddl_conn:
            await bootstrap(ddl_conn)

        async with dml_engine.begin() as dml_conn:
            from dodoo.core.bootstrap import sec005_check
            await sec005_check(dml_conn)

        env = cls(dml_engine, ddl_engine, registry)

        from dodoo.modules.installer import ModuleInstaller

        env.modules = _ModuleFacade(ModuleInstaller(env), env)
        return env

    def __getitem__(self, model_name: str) -> _ModelProxy:
        model = self.registry.lookup(model_name)
        return _ModelProxy(model, self)

    @asynccontextmanager
    async def dml_conn(self) -> AsyncGenerator[AsyncConnection, None]:
        async with get_connection(self._dml_engine) as conn:
            yield conn

    @asynccontextmanager
    async def ddl_conn(self) -> AsyncGenerator[AsyncConnection, None]:
        async with get_connection(self._ddl_engine) as conn:
            yield conn

    async def close(self) -> None:
        await self._dml_engine.dispose()
        await self._ddl_engine.dispose()


class _ModuleFacade:
    def __init__(self, installer: Any, env: Environment) -> None:
        self._installer = installer
        self._env = env

    async def install(self, name: str) -> None:
        await self._installer.install(name)

    async def load_installed(self) -> None:
        await self._installer.load_installed()
