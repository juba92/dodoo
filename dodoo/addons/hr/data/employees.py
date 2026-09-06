"""P1 area — Employees / org structure / tags / contracts / skills.

Registers the P1 models with the ``ir_model`` sync list, the P1 covering indexes, the P1
``ir.rule`` rows, and a sample-data seeder. Imported for side effect by
``dodoo.addons.hr.data.seed``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from dodoo.addons.hr.data import rules, seed
from dodoo.addons.hr.security import GROUP_EMPLOYEE, GROUP_OFFICER

_log = logging.getLogger(__name__)

_MODELS = [
    ("hr.department", "hr_department"),
    ("hr.job", "hr_job"),
    ("hr.employee", "hr_employee"),
    ("hr.employee.category", "hr_employee_category"),
    ("hr.contract.type", "hr_contract_type"),
    ("hr.contract", "hr_contract"),
    ("hr.skill.type", "hr_skill_type"),
    ("hr.skill", "hr_skill"),
    ("hr.skill.level", "hr_skill_level"),
    ("hr.employee.skill", "hr_employee_skill"),
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hr_department_company ON hr_department (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_department_parent ON hr_department (parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_job_company ON hr_job (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_job_published ON hr_job (is_published)",
    "CREATE INDEX IF NOT EXISTS idx_hr_employee_company_name ON hr_employee (company_id, name)",
    "CREATE INDEX IF NOT EXISTS idx_hr_employee_name_pattern ON hr_employee (name text_pattern_ops)",
    "CREATE INDEX IF NOT EXISTS idx_hr_employee_department ON hr_employee (department_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_employee_job ON hr_employee (job_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_employee_manager ON hr_employee (manager_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_hr_employee_user_company "
    "ON hr_employee (user_id, company_id) WHERE user_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_hr_contract_employee_state ON hr_contract (employee_id, state)",
    "CREATE INDEX IF NOT EXISTS idx_hr_contract_company ON hr_contract (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_contract_date_end ON hr_contract (date_end) "
    "WHERE state = 'running'",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_hr_employee_skill "
    "ON hr_employee_skill (employee_id, skill_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_employee_skill_employee ON hr_employee_skill (employee_id)",
]

# ------------------------------------------------------------------- ir.rule
_RULES = [
    # hr.employee — company scope for the Employee group (sensitive columns are dropped in
    # hr.employee.read); full for Officer/Administrator; deny for un-grouped users.
    {
        "name": "hr.employee: company directory (Employee)",
        "model": "hr.employee",
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_EMPLOYEE],
        "perms": "r",
    },
    rules.officer_full("hr.employee"),
    rules.deny_all("hr.employee"),
    # hr.contract — owner reads own; Officer/Administrator full; deny otherwise.
    {
        "name": "hr.contract: own (Employee)",
        "model": "hr.contract",
        "domain": [
            "&",
            ["company_id", "in", "$company_ids"],
            ["employee_id.user_id", "=", "$uid"],
        ],
        "groups": [GROUP_EMPLOYEE],
        "perms": "r",
    },
    rules.officer_full("hr.contract"),
    rules.deny_all("hr.contract"),
    # hr.job / hr.employee.category — visible to all HR groups, managed by Officer+.
    {
        "name": "hr.job: read (HR)",
        "model": "hr.job",
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_EMPLOYEE, GROUP_OFFICER],
        "perms": "r",
    },
    rules.officer_full("hr.job"),
    rules.deny_all("hr.job"),
    rules.deny_all("hr.department"),
    rules.officer_full("hr.department"),
    {
        "name": "hr.department: read (HR)",
        "model": "hr.department",
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_EMPLOYEE, GROUP_OFFICER],
        "perms": "r",
    },
    # Global catalogs — read for any authenticated user, write for Administrator.
    *[
        {
            "name": f"{m}: read (all)",
            "model": m,
            "domain": [[1, "=", 1]],
            "groups": [GROUP_EMPLOYEE, GROUP_OFFICER],
            "perms": "r",
        }
        for m in ("hr.employee.category", "hr.skill.type", "hr.skill", "hr.skill.level")
    ],
    rules.catalog_read("hr.contract.type"),
    rules.catalog_admin_write("hr.contract.type"),
    # hr.employee.skill — via the owning employee, or Officer+.
    {
        "name": "hr.employee.skill: own (Employee)",
        "model": "hr.employee.skill",
        "domain": [["employee_id.user_id", "=", "$uid"]],
        "groups": [GROUP_EMPLOYEE],
        "perms": "r",
    },
    {
        "name": "hr.employee.skill: HR Officer/Administrator full",
        "model": "hr.employee.skill",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_OFFICER],
        "perms": "rwck",
    },
    rules.deny_all("hr.employee.skill"),
]

_CONTRACT_TYPES = ["Permanent", "Fixed-term", "Internship", "Part-time"]

_SKILLS: dict[str, tuple[list[str], list[tuple[str, int]]]] = {
    "Languages": (
        ["English", "Arabic", "French"],
        [("A1", 15), ("A2", 30), ("B1", 50), ("B2", 65), ("C1", 85), ("C2", 100)],
    ),
    "Technical": (
        ["Python", "SQL", "Accounting", "Project Management"],
        [("Novice", 20), ("Intermediate", 50), ("Advanced", 75), ("Expert", 100)],
    ),
}

_DEPARTMENTS = [("Sales", None), ("Field Sales", "Sales"), ("Finance", None), ("HR", None)]
_JOBS = [
    ("Account Executive", "Sales", 3),
    ("Sales Manager", "Sales", 1),
    ("Accountant", "Finance", 2),
    ("HR Officer", "HR", 1),
]


async def seed_employees_area(env: Any) -> None:
    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_company ORDER BY id LIMIT 1"))
        r = row.fetchone()
        if not r:
            _log.warning("hr: no company; skipping P1 sample data")
            return
        company_id = r[0]
        existing = await conn.execute(
            text("SELECT COUNT(*) FROM hr_department WHERE company_id = :c"),
            {"c": company_id},
        )
        if existing.scalar_one() > 0:
            _log.info("hr: P1 sample data already present; skipping")
            return

    from dodoo.addons.hr.models.hr_contract_type import HrContractType
    from dodoo.addons.hr.models.hr_department import HrDepartment
    from dodoo.addons.hr.models.hr_job import HrJob
    from dodoo.addons.hr.models.hr_skill import HrSkill, HrSkillLevel, HrSkillType

    dept_ids: dict[str, int] = {}
    for name, parent in _DEPARTMENTS:
        dept_ids[name] = await HrDepartment.create(
            env,
            {
                "name": name,
                "company_id": company_id,
                "parent_id": dept_ids.get(parent) if parent else None,
            },
        )
    for name, dept, expected in _JOBS:
        await HrJob.create(
            env,
            {
                "name": name,
                "company_id": company_id,
                "department_id": dept_ids.get(dept),
                "expected_employees": expected,
            },
        )
    for name in _CONTRACT_TYPES:
        await HrContractType.create(env, {"name": name})

    for type_name, (skills, levels) in _SKILLS.items():
        type_id = await HrSkillType.create(env, {"name": type_name})
        for i, sk in enumerate(skills):
            await HrSkill.create(
                env, {"name": sk, "skill_type_id": type_id, "sequence": i * 10}
            )
        for i, (lvl, pct) in enumerate(levels):
            await HrSkillLevel.create(
                env,
                {
                    "name": lvl,
                    "skill_type_id": type_id,
                    "level_progress": pct,
                    "sequence": i * 10,
                },
            )
    _log.info("hr: seeded P1 sample data (departments, jobs, contract types, skills)")


# --- register with the seed / rule pipelines (import side effect) ---
seed.IR_MODELS.extend(_MODELS)
seed.INDEXES.extend(_INDEXES)
seed.AREA_SEEDS.append(seed_employees_area)
rules.HR_RULES.extend(_RULES)
