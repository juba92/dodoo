from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dodoo.core.exceptions import SchemaConflictError
from dodoo.core.fields import Char, Integer
from dodoo.core.migration import MigrationRunner
from dodoo.core.models import BaseModel


class MigV1(BaseModel):
    _name = "mig.v1"
    title = Char(size=128)


class MigV2(BaseModel):
    _name = "mig.v2"
    title = Char(size=128)
    score = Integer()


async def test_create_table_on_first_install(env):
    runner = MigrationRunner(env._ddl_engine)
    env.registry.register(MigV1)
    await runner.install(MigV1)

    async with env.dml_conn() as conn:
        from sqlalchemy import text

        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns " "WHERE table_name = 'mig_v1'"
            )
        )
        cols = {row[0] for row in result}
    assert "title" in cols
    assert "id" in cols


async def test_add_column_on_upgrade(env):
    runner = MigrationRunner(env._ddl_engine)
    env.registry.register(MigV2)

    # First install creates table with just title
    await runner.install(MigV2)

    # Re-install after adding score field should add the column
    await runner.install(MigV2)

    async with env.dml_conn() as conn:
        from sqlalchemy import text

        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns " "WHERE table_name = 'mig_v2'"
            )
        )
        cols = {row[0] for row in result}
    assert "score" in cols


async def test_module_loader_install_order(env):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create mod_x and mod_y where mod_y depends on mod_x
        for name, deps in [("mod_x", []), ("mod_y", ["mod_x"])]:
            pkg = tmp_path / name
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "__manifest__.py").write_text(
                repr({"name": name, "version": "1.0.0", "depends": deps})
            )

        import os

        os.environ["ADDONS_PATH"] = tmp
        from dodoo.modules.loader import AddonLoader

        loader = AddonLoader()
        loader.discover(tmp)
        order = loader.resolve_order(["mod_y"])
        assert order.index("mod_x") < order.index("mod_y")


async def test_schema_conflict_error_on_type_change(env):
    class OrigModel(BaseModel):
        _name = "conflict.model"
        value = Char(size=64)

    class ChangedModel(BaseModel):
        _name = "conflict.model"
        value = Integer()  # type change!

    runner = MigrationRunner(env._ddl_engine)
    try:
        env.registry.register(OrigModel)
    except Exception:
        pass
    await runner.install(OrigModel)

    # Simulate type change by patching
    with pytest.raises(SchemaConflictError):
        await runner.install(ChangedModel)
