import pytest
import sqlalchemy as sa

from dodoo.core.exceptions import DomainError
from dodoo.core.fields import Char, Integer
from dodoo.core.query import compile_domain

_META = sa.MetaData()
_TABLE = sa.Table(
    "test_items",
    _META,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(128)),
    sa.Column("qty", sa.Integer()),
    sa.Column("active", sa.Boolean()),
    sa.Column("create_date", sa.DateTime()),
    sa.Column("write_date", sa.DateTime()),
)
_FIELDS = {
    "name": Char(size=128),
    "qty": Integer(),
}


def _str(clause):
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def test_empty_domain_returns_true():
    clause = compile_domain(_TABLE, _FIELDS, [])
    assert "true" in _str(clause).lower() or clause is sa.true()


def test_eq_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["name", "=", "ACME"]])
    sql = _str(clause)
    assert "ACME" in sql


def test_neq_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["name", "!=", "foo"]])
    sql = _str(clause)
    assert "!=" in sql or "NOT" in sql.upper()


def test_lt_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["qty", "<", 10]])
    sql = _str(clause)
    assert "<" in sql


def test_gt_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["qty", ">", 5]])
    sql = _str(clause)
    assert ">" in sql


def test_lte_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["qty", "<=", 10]])
    sql = _str(clause)
    assert "<=" in sql


def test_gte_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["qty", ">=", 1]])
    sql = _str(clause)
    assert ">=" in sql


def test_in_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["name", "in", ["a", "b"]]])
    sql = _str(clause)
    assert "IN" in sql.upper()


def test_not_in_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["name", "not in", ["x"]]])
    sql = _str(clause)
    assert "NOT IN" in sql.upper()


def test_like_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["name", "like", "%test%"]])
    sql = _str(clause)
    assert "LIKE" in sql.upper()


def test_ilike_operator():
    clause = compile_domain(_TABLE, _FIELDS, [["name", "ilike", "%test%"]])
    sql = _str(clause).upper()
    # SA renders ilike as ILIKE (PostgreSQL) or LOWER(x) LIKE LOWER(y) (generic)
    assert "ILIKE" in sql or ("LIKE" in sql and "LOWER" in sql)


def test_or_prefix():
    clause = compile_domain(_TABLE, _FIELDS, ["|", ["name", "=", "a"], ["name", "=", "b"]])
    sql = _str(clause)
    assert "OR" in sql.upper()


def test_empty_domain_is_true():
    result = compile_domain(_TABLE, _FIELDS, [])
    # Should produce SQL that matches everything
    assert result is sa.true() or "true" in str(result).lower()


def test_unknown_field_raises():
    with pytest.raises(DomainError, match="Unknown field"):
        compile_domain(_TABLE, _FIELDS, [["nonexistent_field", "=", "val"]])
