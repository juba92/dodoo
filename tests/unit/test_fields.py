import pytest
import sqlalchemy as sa

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import (
    Boolean,
    Char,
    Date,
    Datetime,
    Float,
    Integer,
    Many2many,
    Many2one,
    One2many,
    Text,
)
from dodoo.core.models import BaseModel


def test_char_col_type():
    f = Char(size=128)
    f.name = "title"
    assert isinstance(f.col_type, sa.String)
    assert f.col_type.length == 128


def test_many2one_relation():
    f = Many2one("res.partner")
    f.name = "partner_id"
    assert f.relation == "res.partner"


def test_required_propagates():
    f = Char(required=True)
    f.name = "code"
    col = f.to_sa_column()
    assert not col.nullable


def test_integer_col():
    f = Integer()
    f.name = "qty"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.Integer)


def test_boolean_col():
    f = Boolean()
    f.name = "active"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.Boolean)


def test_float_col():
    f = Float()
    f.name = "price"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.Float)


def test_date_col():
    f = Date()
    f.name = "order_date"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.Date)


def test_datetime_col():
    f = Datetime()
    f.name = "created_at"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.DateTime)


def test_text_col():
    f = Text()
    f.name = "notes"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.Text)


def test_many2one_fk():
    f = Many2one("res.partner", required=True)
    f.name = "partner_id"
    col = f.to_sa_column()
    assert isinstance(col.type, sa.Integer)
    assert len(col.foreign_keys) == 1


def test_one2many_no_column():
    f = One2many("sale.order", "partner_id")
    f.name = "order_ids"
    assert f.to_sa_column() is None


def test_many2many_no_column():
    f = Many2many("res.groups", "user_groups_rel")
    f.name = "group_ids"
    assert f.to_sa_column() is None


def test_reserved_field_name_id():
    with pytest.raises(DodooError, match="reserved"):

        class BadModel(BaseModel):
            _name = "test.bad.id"
            id = Char()  # type: ignore[assignment]


def test_reserved_field_name_create_date():
    with pytest.raises(DodooError, match="reserved"):

        class BadModel2(BaseModel):
            _name = "test.bad.create_date"
            create_date = Char()  # type: ignore[assignment]


def test_reserved_field_name_write_date():
    with pytest.raises(DodooError, match="reserved"):

        class BadModel3(BaseModel):
            _name = "test.bad.write_date"
            write_date = Char()  # type: ignore[assignment]


def test_humanize_field_label_replaces_underscores_and_titlecases():
    from dodoo.core.models import _humanize

    assert _humanize("invoice_date_due") == "Invoice Date Due"
    assert _humanize("narration") == "Narration"


def test_humanize_field_label_strips_relational_suffixes():
    from dodoo.core.models import _humanize

    assert _humanize("partner_id") == "Partner"
    assert _humanize("tax_ids") == "Tax"


async def test_fields_get_uses_humanized_label_when_no_string(env):
    """A field with no explicit string= gets a humanized, translatable label (not the raw name)."""

    class HumanizeProbe(BaseModel):
        _name = "test.humanize.probe"
        invoice_date_due = Date()

    info = await HumanizeProbe.fields_get(env, attributes=["string"])
    assert info["invoice_date_due"]["string"] == "Invoice Date Due"
