import pytest

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char
from dodoo.core.models import BaseModel
from dodoo.core.registry import ModelRegistry


def _make_registry():
    return ModelRegistry()


def test_register_and_lookup():
    reg = _make_registry()

    class MyModel(BaseModel):
        _name = "my.model"
        title = Char()

    reg.register(MyModel)
    assert reg.lookup("my.model") is MyModel


def test_register_duplicate_raises():
    reg = _make_registry()

    class ModelA(BaseModel):
        _name = "dup.model"
        x = Char()

    reg.register(ModelA)

    class ModelB(BaseModel):
        _name = "dup.model"
        y = Char()

    with pytest.raises(DodooError, match="already registered"):
        reg.register(ModelB)


def test_lookup_missing_raises():
    reg = _make_registry()
    with pytest.raises(DodooError, match="not registered"):
        reg.lookup("does.not.exist")


def test_all_models():
    reg = _make_registry()

    class M1(BaseModel):
        _name = "reg.m1"

    class M2(BaseModel):
        _name = "reg.m2"

    reg.register(M1)
    reg.register(M2)
    models = reg.all_models()
    assert M1 in models
    assert M2 in models


def test_sti_records_parent():
    reg = _make_registry()

    class Parent(BaseModel):
        _name = "sti.parent"
        label = Char()

    class Child(BaseModel):
        _name = "sti.child"
        _inherit = "sti.parent"
        extra = Char()

    reg.register(Parent)
    reg.register(Child)
    assert reg.parent_of("sti.child") == "sti.parent"
    assert reg.is_child("sti.child")
    assert not reg.is_child("sti.parent")
