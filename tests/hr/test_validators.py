"""US1 — HTTP-boundary whitelist validators (FR-065). Pure — runs without a database."""

from __future__ import annotations

import pytest

from dodoo.addons.hr.validators import (
    AllocationCreate,
    ContractCreate,
    ContractSetState,
    DepartmentCreate,
    EmployeeCreate,
    LeaveCreate,
    PublicHolidayCreate,
    validate,
)
from dodoo.core.exceptions import DodooError


def test_unknown_field_rejected():
    with pytest.raises(DodooError, match="unknown_field"):
        validate(EmployeeCreate, {"name": "X", "company_id": 1, "salary": 999})


def test_missing_required_rejected():
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(EmployeeCreate, {"company_id": 1})


def test_out_of_range_rejected():
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(DepartmentCreate, {"name": "X", "company_id": 1, "appraisal_frequency_months": 0})
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(ContractCreate, {"name": "c", "employee_id": 1, "company_id": 1, "date_start": "2026-01-01", "wage": -5})


def test_bad_enum_rejected():
    with pytest.raises(DodooError):
        validate(EmployeeCreate, {"name": "X", "company_id": 1, "gender": "yes"})
    with pytest.raises(DodooError):
        validate(ContractSetState, {"state": "archived"})


def test_contract_date_cross_field_rejected():
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(
            ContractCreate,
            {"name": "c", "employee_id": 1, "company_id": 1, "date_start": "2026-06-01", "date_end": "2026-01-01"},
        )


def test_p2_cross_field_rules():
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(
            AllocationCreate,
            {"employee_id": 1, "leave_type_id": 1, "company_id": 1, "mode": "accrual"},
        )
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(
            LeaveCreate,
            {"employee_id": 1, "leave_type_id": 1, "date_from": "2026-06-05T00:00:00", "date_to": "2026-06-01T00:00:00"},
        )
    with pytest.raises(DodooError, match="invalid_payload"):
        validate(PublicHolidayCreate, {"name": "x", "date_from": "2026-06-05", "date_to": "2026-06-01"})


def test_p2_valid_payloads_pass():
    validate(
        AllocationCreate,
        {"employee_id": 1, "leave_type_id": 1, "company_id": 1, "mode": "accrual", "accrual_rate": 1, "accrual_period": "month"},
    )
    m = validate(
        LeaveCreate,
        {"employee_id": 1, "leave_type_id": 1, "date_from": "2026-06-01T00:00:00", "date_to": "2026-06-05T00:00:00"},
    )
    assert m.employee_id == 1


def test_valid_payloads_pass():
    validate(EmployeeCreate, {"name": "Ada Lovelace", "company_id": 1, "gender": "female"})
    validate(
        ContractCreate,
        {"name": "Perm", "employee_id": 2, "company_id": 1, "date_start": "2026-01-01", "date_end": "2026-12-31"},
    )
    m = validate(ContractSetState, {"state": "running", "expected_state": "draft"})
    assert m.state == "running"
