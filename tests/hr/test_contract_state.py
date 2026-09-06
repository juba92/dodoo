"""US1 — contract-state engine (ADR-024).

Pure-logic tests (transition table, date guards, derived expiry) run without a database.
The DB-backed workflow (`action_set_state`, one-running guard, `run_contract_expiry`,
`get_running_contract`) is covered by the `env`-fixtured tests, which skip without Postgres.
"""

from __future__ import annotations

import datetime

import pytest

from dodoo.addons.hr.models.hr_contract import _TRANSITIONS, HrContract
from dodoo.core.exceptions import DodooError

# ---- pure logic (no DB) ------------------------------------------------------


def test_transition_table_shape():
    assert _TRANSITIONS["draft"] == {"running", "cancelled"}
    assert _TRANSITIONS["running"] == {"expired", "cancelled"}
    assert _TRANSITIONS["expired"] == {"draft"}
    assert _TRANSITIONS["cancelled"] == {"draft"}
    # no path back into running except from draft
    assert "running" not in _TRANSITIONS["expired"]
    assert "running" not in _TRANSITIONS["cancelled"]


def test_effective_state_flags_past_end_running():
    row = {"state": "running", "date_end": "2000-01-01"}
    assert HrContract._effective_state(row) == "expired"


def test_effective_state_keeps_open_running():
    future = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
    assert HrContract._effective_state({"state": "running", "date_end": future}) == "running"
    assert HrContract._effective_state({"state": "running", "date_end": None}) == "running"


def test_effective_state_passthrough_for_non_running():
    for s in ("draft", "expired", "cancelled"):
        assert HrContract._effective_state({"state": s, "date_end": "2000-01-01"}) == s


def test_check_dates_rejects_end_before_start():
    with pytest.raises(DodooError, match="contract_dates"):
        HrContract._check_dates({"date_start": "2026-06-01", "date_end": "2026-05-01"})


def test_check_dates_rejects_trial_outside_window():
    with pytest.raises(DodooError, match="contract_trial"):
        HrContract._check_dates(
            {"date_start": "2026-01-01", "date_end": "2026-12-31", "trial_date_end": "2025-12-01"}
        )
    with pytest.raises(DodooError, match="contract_trial"):
        HrContract._check_dates(
            {"date_start": "2026-01-01", "date_end": "2026-06-30", "trial_date_end": "2026-07-15"}
        )


def test_check_dates_accepts_valid():
    HrContract._check_dates(
        {"date_start": "2026-01-01", "date_end": "2026-12-31", "trial_date_end": "2026-03-01"}
    )
    HrContract._check_dates({"date_start": "2026-01-01"})  # open-ended, no trial


# ---- DB-backed workflow (skips without Postgres) ---------------------------


@pytest.fixture
async def _p1(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    emp = await HrEmployee.create(env, {"name": "Contract Test", "company_id": company_id})
    return {"company_id": company_id, "employee_id": emp}


async def test_set_state_follows_transition_table(env, _p1):
    from dodoo.addons.hr.models.hr_contract import HrContract as Contract

    cid = await Contract.create(
        env,
        {
            "name": "C1",
            "employee_id": _p1["employee_id"],
            "company_id": _p1["company_id"],
            "date_start": "2026-01-01",
        },
    )
    await Contract.action_set_state(env, [cid], "running", uid=1)
    rows = await Contract.read(env, [cid], ["state"])
    assert rows[0]["state"] == "running"

    with pytest.raises(DodooError, match="contract_transition_invalid"):
        await Contract.action_set_state(env, [cid], "draft", uid=1)


async def test_set_state_conflict_on_stale_expected(env, _p1):
    from dodoo.addons.hr.models.hr_contract import HrContract as Contract

    cid = await Contract.create(
        env,
        {
            "name": "C2",
            "employee_id": _p1["employee_id"],
            "company_id": _p1["company_id"],
            "date_start": "2026-01-01",
        },
    )
    with pytest.raises(DodooError, match="contract_state_conflict"):
        await Contract.action_set_state(env, [cid], "running", uid=1, expected_state="running")


async def test_only_one_running_contract(env, _p1):
    from dodoo.addons.hr.models.hr_contract import HrContract as Contract

    a = await Contract.create(
        env,
        {"name": "A", "employee_id": _p1["employee_id"], "company_id": _p1["company_id"], "date_start": "2026-01-01"},
    )
    b = await Contract.create(
        env,
        {"name": "B", "employee_id": _p1["employee_id"], "company_id": _p1["company_id"], "date_start": "2026-02-01"},
    )
    await Contract.action_set_state(env, [a], "running", uid=1)
    with pytest.raises(DodooError, match="contract_running_exists"):
        await Contract.action_set_state(env, [b], "running", uid=1)


async def test_run_contract_expiry_is_idempotent(env, _p1):
    from dodoo.addons.hr.models.hr_contract import HrContract as Contract

    cid = await Contract.create(
        env,
        {
            "name": "Old",
            "employee_id": _p1["employee_id"],
            "company_id": _p1["company_id"],
            "date_start": "2020-01-01",
            "date_end": "2020-12-31",
        },
    )
    await Contract.action_set_state(env, [cid], "running", uid=1)
    first = await Contract.run_contract_expiry(env)
    assert first["expired"] == 1
    second = await Contract.run_contract_expiry(env)
    assert second["expired"] == 0
