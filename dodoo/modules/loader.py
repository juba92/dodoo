from __future__ import annotations

import logging
from graphlib import CycleError as _GraphCycleError
from graphlib import TopologicalSorter
from pathlib import Path

from dodoo.core.exceptions import CycleError, ModuleLoadError

_log = logging.getLogger(__name__)

_REQUIRED_KEYS = {"name", "version", "depends"}


class AddonLoader:
    def __init__(self) -> None:
        self._manifests: dict[str, dict] = {}

    def discover(self, addons_path: str) -> dict[str, dict]:
        path = Path(addons_path)
        if not path.exists():
            _log.warning("ADDONS_PATH '%s' does not exist; no add-ons discovered", addons_path)
            return {}
        if not any(path.iterdir()) if path.is_dir() else True:
            _log.warning("ADDONS_PATH '%s' is empty; no add-ons discovered", addons_path)

        manifests: dict[str, dict] = {}
        for entry in sorted(path.iterdir()):
            if not entry.is_dir():
                continue
            manifest_file = entry / "__manifest__.py"
            if not manifest_file.exists():
                continue
            try:
                manifest = _load_manifest(manifest_file)
            except ModuleLoadError:
                raise
            except Exception as exc:
                raise ModuleLoadError(f"Failed to load manifest at {manifest_file}: {exc}") from exc
            manifests[entry.name] = manifest

        self._manifests = manifests
        return manifests

    def resolve_order(self, names: list[str]) -> list[str]:
        graph: dict[str, set[str]] = {}

        def _collect(name: str) -> None:
            if name in graph:
                return
            manifest = self._manifests.get(name)
            if manifest is None:
                raise ModuleLoadError(f"Module '{name}' not found in discovered add-ons")
            deps = manifest.get("depends", [])
            graph[name] = set(deps)
            for dep in deps:
                _collect(dep)

        for n in names:
            _collect(n)

        sorter = TopologicalSorter(graph)
        try:
            return list(sorter.static_order())
        except _GraphCycleError as exc:
            raise CycleError(f"Circular dependency detected: {exc}") from exc


def _load_manifest(path: Path) -> dict:
    import ast

    with open(path) as fh:
        source = fh.read()

    try:
        manifest = ast.literal_eval(source.strip())
    except Exception as exc:
        raise ModuleLoadError(f"Manifest at {path} is not a valid Python literal: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ModuleLoadError(f"Manifest at {path} must be a dict")

    missing = _REQUIRED_KEYS - manifest.keys()
    if missing:
        raise ModuleLoadError(f"Manifest at {path} is missing required keys: {missing}")

    return manifest
