from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dodoo.core.exceptions import ModuleLoadError
from dodoo.core.migration import MigrationRunner
from dodoo.modules.loader import AddonLoader

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class ModuleInstaller:
    def __init__(self, env: Environment) -> None:
        self._env = env
        self._loader = AddonLoader()
        self._runner: MigrationRunner | None = None

    def _get_runner(self) -> MigrationRunner:
        if self._runner is None:
            self._runner = MigrationRunner(self._env._ddl_engine)
        return self._runner

    async def install(self, name: str) -> None:
        import os

        addons_path = os.environ.get("ADDONS_PATH", "./addons")

        # Include built-in addons path
        builtin_addons = str(Path(__file__).parent.parent / "addons")
        paths = [builtin_addons] + [p.strip() for p in addons_path.split(":") if p.strip()]

        # Discover from all paths
        all_manifests: dict[str, dict] = {}
        for path in paths:
            self._loader.discover(path)
            all_manifests.update(self._loader._manifests)
        self._loader._manifests = all_manifests

        if name not in all_manifests:
            raise ModuleLoadError(f"Module '{name}' not found in any add-ons directory")

        order = self._loader.resolve_order([name])

        for mod_name in order:
            await self._install_single(mod_name, paths)

    async def _install_single(self, name: str, paths: list[str]) -> None:
        # Find the package directory
        pkg_dir: Path | None = None
        for path in paths:
            candidate = Path(path) / name
            if candidate.is_dir() and (candidate / "__manifest__.py").exists():
                pkg_dir = candidate
                break

        if pkg_dir is None:
            raise ModuleLoadError(f"Module '{name}' directory not found")

        manifest = self._loader._manifests[name]

        # Import the package (makes models register themselves via metaclass)
        _import_package(pkg_dir)

        # Run migration for all models registered by this package
        runner = self._get_runner()

        for model_cls in self._env.registry.all_models():
            await runner.install(model_cls)

        # Handle STI discriminator columns
        for model_cls in self._env.registry.all_models():
            if model_cls._inherit:
                parent_cls = self._env.registry.lookup(model_cls._inherit)
                await runner.add_discriminator(parent_cls._table_name())

        _log.info("Installed module '%s' version %s", name, manifest.get("version", "?"))


def _import_package(pkg_dir: Path) -> None:
    pkg_name = pkg_dir.name
    parent_dir = str(pkg_dir.parent)

    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    try:
        if pkg_name in sys.modules:
            return
        importlib.import_module(pkg_name)
    except ImportError as exc:
        raise ModuleLoadError(f"Failed to import module '{pkg_name}': {exc}") from exc
