from dodoo.core.fields import Boolean, Char, Many2one, Text
from dodoo.core.models import BaseModel


class IrModule(BaseModel):
    _name = "ir.module"

    name = Char(size=128, required=True)
    version = Char(size=64)
    state = Char(size=32, default="uninstalled")
    installed_version = Char(size=64)
    depends = Text()


class IrModel(BaseModel):
    _name = "ir.model"

    name = Char(size=128, required=True)
    table_name = Char(size=128, required=True)
    module_id = Many2one("ir.module")
    description = Text()


class IrModelField(BaseModel):
    _name = "ir.model.field"

    model_id = Many2one("ir.model", required=True)
    name = Char(size=64, required=True)
    field_type = Char(size=32, required=True)
    string = Char(size=128)
    required = Boolean()
    readonly = Boolean()
    default_val = Text()
    relation = Char(size=128)
    relation_field = Char(size=64)
    relation_table = Char(size=128)
