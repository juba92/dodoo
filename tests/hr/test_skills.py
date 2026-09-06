"""US1 — skills taxonomy guards (FR-017…FR-019)."""

from __future__ import annotations

import pytest

from dodoo.addons.hr.models.hr_skill import _check_progress
from dodoo.core.exceptions import DodooError


def test_progress_range_guard():
    _check_progress(0)
    _check_progress(100)
    _check_progress(None)
    with pytest.raises(DodooError, match="skill_level_progress_range"):
        _check_progress(101)
    with pytest.raises(DodooError, match="skill_level_progress_range"):
        _check_progress(-1)


@pytest.fixture
async def _skills(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_skill import HrSkill, HrSkillLevel, HrSkillType

    t1 = await HrSkillType.create(env, {"name": "T1"})
    t2 = await HrSkillType.create(env, {"name": "T2"})
    s1 = await HrSkill.create(env, {"name": "S1", "skill_type_id": t1})
    lvl_t1 = await HrSkillLevel.create(env, {"name": "L", "skill_type_id": t1, "level_progress": 50})
    lvl_t2 = await HrSkillLevel.create(env, {"name": "L", "skill_type_id": t2, "level_progress": 50})
    emp = await HrEmployee.create(env, {"name": "Skilled", "company_id": company_id})
    return {"skill": s1, "lvl_t1": lvl_t1, "lvl_t2": lvl_t2, "emp": emp}


async def test_level_must_match_skill_type(env, _skills):
    from dodoo.addons.hr.models.hr_skill import HrEmployeeSkill

    with pytest.raises(DodooError, match="skill_level_mismatch"):
        await HrEmployeeSkill.create(
            env,
            {
                "employee_id": _skills["emp"],
                "skill_id": _skills["skill"],
                "skill_level_id": _skills["lvl_t2"],
            },
        )


async def test_no_duplicate_skill_per_employee(env, _skills):
    from dodoo.addons.hr.models.hr_skill import HrEmployeeSkill

    payload = {
        "employee_id": _skills["emp"],
        "skill_id": _skills["skill"],
        "skill_level_id": _skills["lvl_t1"],
    }
    await HrEmployeeSkill.create(env, payload)
    with pytest.raises(DodooError, match="skill_duplicate"):
        await HrEmployeeSkill.create(env, payload)


async def test_employee_skill_denormalises_type(env, _skills):
    from dodoo.addons.hr.models.hr_skill import HrEmployeeSkill

    rec = await HrEmployeeSkill.create(
        env,
        {
            "employee_id": _skills["emp"],
            "skill_id": _skills["skill"],
            "skill_level_id": _skills["lvl_t1"],
        },
    )
    rows = await HrEmployeeSkill.read(env, [rec], ["skill_type_id"])
    assert rows[0]["skill_type_id"] is not None
