"""Unit tests for the record-rule domain engine extensions (ADR-028).

Covers ``$``-placeholder substitution, dotted-path relational leaves, NULL handling, and
the operator-list still rejecting unknown fields / operators. No database — synthetic
``sa.Table`` objects and a hand-built resolver.
"""

import pytest
import sqlalchemy as sa

from dodoo.core.exceptions import DomainError
from dodoo.core.fields import Char, Many2one
from dodoo.core.query import compile_domain

_META = sa.MetaData()

_LEAVE = sa.Table(
    "hr_leave",
    _META,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("company_id", sa.Integer()),
    sa.Column("employee_id", sa.Integer()),
    sa.Column("state", sa.String(64)),
)
_EMPLOYEE = sa.Table(
    "hr_employee",
    _META,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("user_id", sa.Integer()),
    sa.Column("manager_id", sa.Integer()),
)

_LEAVE_FIELDS = {
    "company_id": Many2one("res.company"),
    "employee_id": Many2one("hr.employee"),
    "state": Char(size=64),
}
_EMPLOYEE_FIELDS = {
    "user_id": Many2one("res.users"),
    "manager_id": Many2one("hr.employee"),
}


def _resolve(model_name: str):
    return {
        "hr.employee": (_EMPLOYEE, _EMPLOYEE_FIELDS),
    }[model_name]


def _sql(clause) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


# ---- placeholder substitution ------------------------------------------------


def test_uid_placeholder_substituted():
    clause = compile_domain(
        _LEAVE, _LEAVE_FIELDS, [["employee_id", "=", "$uid"]], context={"uid": 7}
    )
    assert "= 7" in _sql(clause)


def test_company_ids_placeholder_in_list_op():
    clause = compile_domain(
        _LEAVE,
        _LEAVE_FIELDS,
        [["company_id", "in", "$company_ids"]],
        context={"company_ids": [1, 2]},
    )
    sql = _sql(clause).upper()
    assert "IN (1, 2)" in sql


def test_placeholder_inside_explicit_list():
    clause = compile_domain(
        _LEAVE,
        _LEAVE_FIELDS,
        [["employee_id", "in", ["$uid", 99]]],
        context={"uid": 3},
    )
    assert "IN (3, 99)" in _sql(clause).upper()


def test_today_placeholder_needs_no_context():
    clause = compile_domain(_LEAVE, _LEAVE_FIELDS, [["state", "=", "$today"]])
    # renders as a date literal, not the token
    assert "$today" not in _sql(clause)


def test_unknown_placeholder_raises():
    with pytest.raises(DomainError, match="placeholder"):
        compile_domain(
            _LEAVE, _LEAVE_FIELDS, [["employee_id", "=", "$bogus"]], context={"uid": 1}
        )


def test_literal_value_without_dollar_is_untouched():
    clause = compile_domain(_LEAVE, _LEAVE_FIELDS, [["state", "=", "approved"]])
    assert "approved" in _sql(clause)


# ---- dotted-path relational leaves -----------------------------------------


def test_one_hop_relation_compiles_to_subquery():
    clause = compile_domain(
        _LEAVE,
        _LEAVE_FIELDS,
        [["employee_id.user_id", "=", "$uid"]],
        context={"uid": 5},
        resolve=_resolve,
    )
    sql = _sql(clause).upper()
    assert "IN (SELECT" in sql and "HR_EMPLOYEE" in sql and "USER_ID = 5" in sql


def test_two_hop_relation_manager_chain():
    clause = compile_domain(
        _LEAVE,
        _LEAVE_FIELDS,
        [["employee_id.manager_id.user_id", "=", "$uid"]],
        context={"uid": 5},
        resolve=_resolve,
    )
    sql = _sql(clause).upper()
    assert sql.count("SELECT") >= 2  # nested subqueries, one per hop


def test_relation_leaf_without_resolver_raises():
    with pytest.raises(DomainError, match="resolver"):
        compile_domain(
            _LEAVE, _LEAVE_FIELDS, [["employee_id.user_id", "=", 1]], context={}
        )


def test_dotted_head_must_be_many2one():
    with pytest.raises(DomainError, match="Many2one head"):
        compile_domain(
            _LEAVE,
            _LEAVE_FIELDS,
            [["state.foo", "=", 1]],
            resolve=_resolve,
        )


# ---- NULL handling -------------------------------------------------------------


def test_eq_none_is_null():
    clause = compile_domain(_LEAVE, _LEAVE_FIELDS, [["employee_id", "=", None]])
    assert "IS NULL" in _sql(clause).upper()


def test_neq_none_is_not_null():
    clause = compile_domain(_LEAVE, _LEAVE_FIELDS, [["employee_id", "!=", None]])
    assert "IS NOT NULL" in _sql(clause).upper()


# ---- combinators still work with the new leaf path ---------------------------


def test_or_of_owner_and_manager_rule():
    clause = compile_domain(
        _LEAVE,
        _LEAVE_FIELDS,
        [
            "&",
            ["company_id", "in", "$company_ids"],
            "|",
            ["employee_id.user_id", "=", "$uid"],
            ["employee_id.manager_id.user_id", "=", "$uid"],
        ],
        context={"uid": 5, "company_ids": [1]},
        resolve=_resolve,
    )
    sql = _sql(clause).upper()
    assert " OR " in sql and " AND " in sql


def test_unknown_field_still_raises():
    with pytest.raises(DomainError, match="Unknown field"):
        compile_domain(_LEAVE, _LEAVE_FIELDS, [["nope", "=", 1]])
