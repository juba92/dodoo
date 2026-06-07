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
        paths = [builtin_addons] + [
            p.strip() for p in addons_path.split(":") if p.strip()
        ]

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

    async def load_installed(self) -> None:
        """Import packages for all installed modules (server startup — no migrations)."""
        import os

        from sqlalchemy import text

        addons_path = os.environ.get("ADDONS_PATH", "./addons")
        builtin_addons = str(Path(__file__).parent.parent / "addons")
        paths = [builtin_addons] + [
            p.strip() for p in addons_path.split(":") if p.strip()
        ]

        for path in paths:
            discovered = self._loader.discover(path)
            self._loader._manifests.update(discovered)

        async with self._env.dml_conn() as conn:
            result = await conn.execute(
                text("SELECT name FROM ir_module WHERE state = 'installed'")
            )
            installed = [row[0] for row in result.fetchall()]

        from dodoo.core.models import _ALL_MODELS

        for name in installed:
            for path in paths:
                pkg_dir = Path(path) / name
                if pkg_dir.is_dir() and (pkg_dir / "__manifest__.py").exists():
                    before = set(id(m) for m in _ALL_MODELS)
                    _import_package(pkg_dir)
                    for model_cls in _ALL_MODELS:
                        if (
                            id(model_cls) not in before
                            and not getattr(model_cls, "_abstract", False)
                            and model_cls._name
                        ):
                            try:
                                self._env.registry.register(model_cls)
                            except Exception:
                                pass
                    break

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

        from dodoo.core.models import _ALL_MODELS

        before = set(id(m) for m in _ALL_MODELS)

        # Import the package (makes models register themselves via metaclass)
        _import_package(pkg_dir)

        # Register any models newly defined by this package (skip abstract ones)
        for model_cls in _ALL_MODELS:
            if (
                id(model_cls) not in before
                and not getattr(model_cls, "_abstract", False)
                and model_cls._name
            ):
                try:
                    self._env.registry.register(model_cls)
                except Exception:
                    pass  # already registered (re-install scenario)

        # Run migration for all models registered by this package
        runner = self._get_runner()

        for model_cls in self._env.registry.all_models():
            await runner.install(model_cls)

        # Handle STI discriminator columns
        for model_cls in self._env.registry.all_models():
            if model_cls._inherit:
                parent_cls = self._env.registry.lookup(model_cls._inherit)
                await runner.add_discriminator(parent_cls._table_name())

        from sqlalchemy import text

        version = manifest.get("version", "1.0.0")
        application = bool(manifest.get("application", False))
        async with self._env.dml_conn() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ir_module (name, version, state, installed_version, depends, application)"
                    " VALUES (:name, :version, 'installed', :version, :depends, :application)"
                    " ON CONFLICT (name) DO UPDATE SET"
                    "   state = 'installed',"
                    "   installed_version = :version,"
                    "   application = :application,"
                    "   write_date = now()"
                ),
                {
                    "name": name,
                    "version": version,
                    "depends": ",".join(manifest.get("depends", [])),
                    "application": application,
                },
            )

        # Call post_install hook if the package defines one
        pkg_module = (
            importlib.import_module(f"dodoo.addons.{name}")
            if (Path(__file__).parent.parent / "addons" / name).is_dir()
            else sys.modules.get(name)
        )

        if pkg_module is not None:
            post_install = getattr(pkg_module, "post_install", None)
            if callable(post_install):
                await post_install(self._env)

        _log.info("Installed module '%s' version %s", name, version)


def _import_package(pkg_dir: Path) -> None:
    pkg_name = pkg_dir.name
    dodoo_addons_dir = Path(__file__).parent.parent / "addons"

    if pkg_dir.parent.resolve() == dodoo_addons_dir.resolve():
        # Built-in addon — import as dodoo.addons.<name> so relative imports work
        full_name = f"dodoo.addons.{pkg_name}"
        if full_name in sys.modules:
            return
        try:
            importlib.import_module(full_name)
        except ImportError as exc:
            raise ModuleLoadError(
                f"Failed to import built-in module '{full_name}': {exc}"
            ) from exc
        return

    # External addon — add parent dir to sys.path and import by bare name
    parent_dir = str(pkg_dir.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    try:
        if pkg_name in sys.modules:
            return
        importlib.import_module(pkg_name)
    except ImportError as exc:
        raise ModuleLoadError(f"Failed to import module '{pkg_name}': {exc}") from exc
