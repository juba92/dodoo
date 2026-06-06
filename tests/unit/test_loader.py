import tempfile
from pathlib import Path

import pytest

from dodoo.core.exceptions import CycleError, ModuleLoadError
from dodoo.modules.loader import AddonLoader


def _make_addon(base: Path, name: str, depends: list[str]) -> Path:
    pkg = base / name
    pkg.mkdir()
    manifest = {"name": name, "version": "1.0.0", "depends": depends}
    (pkg / "__manifest__.py").write_text(repr(manifest))
    (pkg / "__init__.py").write_text("")
    return pkg


def test_valid_manifest_passes():
    with tempfile.TemporaryDirectory() as tmp:
        _make_addon(Path(tmp), "mod_a", [])
        loader = AddonLoader()
        result = loader.discover(tmp)
        assert "mod_a" in result
        assert result["mod_a"]["name"] == "mod_a"


def test_missing_depends_raises():
    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "bad_mod"
        pkg.mkdir()
        (pkg / "__manifest__.py").write_text('{"name": "bad_mod", "version": "1.0"}')
        (pkg / "__init__.py").write_text("")
        loader = AddonLoader()
        with pytest.raises(ModuleLoadError, match="depends"):
            loader.discover(tmp)


def test_topological_sort_abc():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _make_addon(tmp_path, "mod_a", [])
        _make_addon(tmp_path, "mod_b", ["mod_a"])
        _make_addon(tmp_path, "mod_c", ["mod_b"])
        loader = AddonLoader()
        loader.discover(tmp)
        order = loader.resolve_order(["mod_c"])
        assert order.index("mod_a") < order.index("mod_b")
        assert order.index("mod_b") < order.index("mod_c")


def test_cycle_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _make_addon(tmp_path, "cycle_a", ["cycle_b"])
        _make_addon(tmp_path, "cycle_b", ["cycle_a"])
        loader = AddonLoader()
        loader.discover(tmp)
        with pytest.raises(CycleError):
            loader.resolve_order(["cycle_a"])


def test_missing_dependency_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _make_addon(tmp_path, "needs_ghost", ["ghost_mod"])
        loader = AddonLoader()
        loader.discover(tmp)
        with pytest.raises(ModuleLoadError, match="ghost_mod"):
            loader.resolve_order(["needs_ghost"])


def test_nonexistent_addons_path_returns_empty():
    loader = AddonLoader()
    result = loader.discover("/nonexistent/path/12345")
    assert result == {}


def test_empty_addons_path_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        loader = AddonLoader()
        result = loader.discover(tmp)
        assert result == {}
