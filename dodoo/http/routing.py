from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from dodoo.core.exceptions import RouteConflictError

_log = logging.getLogger(__name__)

_PROTECTED_PATHS = {"/web/session/authenticate", "/web/session/logout", "/web/health"}


class RouteRegistry:
    _instance: RouteRegistry | None = None

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], dict[str, Any]] = {}

    @classmethod
    def get(cls) -> RouteRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Used in tests to clear registered routes between test sessions."""
        cls._instance = None

    def add_route(
        self,
        path: str,
        methods: list[str],
        handler: Callable,
        auth: str = "session",
    ) -> None:
        for method in methods:
            key = (method.upper(), path)
            if key in self._routes:
                raise RouteConflictError(
                    f"Route conflict: {method.upper()} {path} is already registered"
                )
            self._routes[key] = {"handler": handler, "auth": auth, "path": path}

    def remove_route(self, path: str, methods: list[str]) -> None:
        for method in methods:
            key = (method.upper(), path)
            self._routes.pop(key, None)

    def register_with_app(self, app: FastAPI) -> None:
        for (method, path), info in self._routes.items():
            app.add_api_route(
                path,
                info["handler"],
                methods=[method],
            )
            _log.debug("Registered route %s %s (auth=%s)", method, path, info["auth"])


class MountRegistry:
    _instance: MountRegistry | None = None

    def __init__(self) -> None:
        self._mounts: list[tuple[str, Any, str]] = []

    @classmethod
    def get(cls) -> MountRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def add_mount(self, path: str, mount_app: Any, name: str) -> None:
        self._mounts.append((path, mount_app, name))

    def register_with_app(self, app: FastAPI) -> None:
        for path, mount_app, name in self._mounts:
            app.mount(path, mount_app, name=name)
            _log.debug("Mounted %s at %s", name, path)


def route(path: str, methods: list[str], auth: str = "session") -> Callable:
    """Decorator for registering a REST route with the global RouteRegistry."""

    def decorator(fn: Callable) -> Callable:
        RouteRegistry.get().add_route(path, methods, fn, auth=auth)
        return fn

    return decorator
