from __future__ import annotations

import pytest

from dodoo.core.fields import Char, Integer, Many2one
from dodoo.core.migration import MigrationRunner
from dodoo.core.models import BaseModel


class TestContact(BaseModel):
    _name = "test.contact"
    name = Char(size=256, required=True)
    email = Char(size=256)
    age = Integer()


class TestCompany(BaseModel):
    _name = "test.company"
    company_name = Char(size=256, required=True)


class TestContactWithFK(BaseModel):
    _name = "test.contact.fk"
    name = Char(size=256, required=True)
    company_id = Many2one("test.company")


class TestParent(BaseModel):
    _name = "test.parent"
    label = Char(size=128)


class TestChild(BaseModel):
    _name = "test.child"
    _inherit = "test.parent"
    extra = Char(size=128)


@pytest.fixture(scope="module", autouse=True)
async def setup_tables(env):
    runner = MigrationRunner(env._ddl_engine)
    for cls in [TestContact, TestCompany, TestContactWithFK, TestParent, TestChild]:
        env.registry.register(cls)
        await runner.install(cls)
    await runner.add_discriminator(TestParent._table_name())


async def test_create_and_read(env):
    rec_id = await TestContact.create(env, {"name": "ACME Corp", "email": "acme@example.com"})
    assert isinstance(rec_id, int) and rec_id > 0

    records = await TestContact.read(env, [rec_id])
    assert len(records) == 1
    assert records[0]["name"] == "ACME Corp"
    assert records[0]["email"] == "acme@example.com"


async def test_write(env):
    rec_id = await TestContact.create(env, {"name": "Old Name"})
    await TestContact.write(env, [rec_id], {"name": "New Name"})
    records = await TestContact.read(env, [rec_id], ["name"])
    assert records[0]["name"] == "New Name"


async def test_unlink(env):
    rec_id = await TestContact.create(env, {"name": "To Delete"})
    await TestContact.unlink(env, [rec_id])
    records = await TestContact.read(env, [rec_id])
    assert records == []


async def test_search_with_domain(env):
    await TestContact.create(env, {"name": "ACME Industries"})
    await TestContact.create(env, {"name": "Globex Corp"})

    ids = await TestContact.search(env, [["name", "ilike", "acme%"]])
    records = await TestContact.read(env, ids, ["name"])
    names = {r["name"] for r in records}
    assert "ACME Industries" in names
    assert "Globex Corp" not in names


async def test_many2one_fk_invalid_parent_rejected(env):
    with pytest.raises(Exception):
        await TestContactWithFK.create(env, {"name": "Bad FK", "company_id": 999999})


async def test_sti_child_and_parent(env):
    parent_id = await TestParent.create(env, {"label": "Base record"})
    child_id = await TestChild.create(env, {"label": "Child record", "extra": "child data"})

    parent_records = await TestParent.search(env, [])
    child_records = await TestChild.search(env, [])

    parent_ids_set = set(parent_records)
    child_ids_set = set(child_records)

    assert parent_id in parent_ids_set
    assert child_id in child_ids_set
    # STI: child query should not return parent-only records
    assert parent_id not in child_ids_set


async def test_search_read(env):
    await TestContact.create(env, {"name": "SearchRead Test", "age": 42})
    results = await TestContact.search_read(
        env, [["name", "=", "SearchRead Test"]], fields=["name", "age"]
    )
    assert any(r["name"] == "SearchRead Test" and r["age"] == 42 for r in results)
