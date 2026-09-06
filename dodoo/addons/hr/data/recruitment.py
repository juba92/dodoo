"""P3 area — Recruitment (job publish flag, stages, sources, applicants, refuse reasons)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from dodoo.addons.hr.data import rules, seed
from dodoo.addons.hr.security import GROUP_EMPLOYEE, GROUP_OFFICER

_log = logging.getLogger(__name__)

_MODELS = [
    ("hr.recruitment.stage", "hr_recruitment_stage"),
    ("hr.recruitment.source", "hr_recruitment_source"),
    ("hr.applicant.refuse.reason", "hr_applicant_refuse_reason"),
    ("hr.applicant", "hr_applicant"),
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hr_applicant_job_stage ON hr_applicant (job_id, stage_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_applicant_company ON hr_applicant (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_applicant_refused ON hr_applicant (refused)",
    "CREATE INDEX IF NOT EXISTS idx_hr_recruitment_stage_seq ON hr_recruitment_stage (sequence)",
]

_RULES = [
    # hr.applicant — company-scoped for Officer/Administrator; deny for plain Employee.
    rules.officer_full("hr.applicant"),
    rules.deny_all("hr.applicant"),
    # catalogs
    rules.catalog_read("hr.recruitment.stage"),
    rules.catalog_admin_write("hr.recruitment.stage"),
    rules.catalog_read("hr.recruitment.source"),
    rules.catalog_admin_write("hr.recruitment.source"),
    {
        "name": "hr.applicant.refuse.reason: read (HR)",
        "model": "hr.applicant.refuse.reason",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_EMPLOYEE, GROUP_OFFICER],
        "perms": "r",
    },
    {
        "name": "hr.applicant.refuse.reason: write (Officer)",
        "model": "hr.applicant.refuse.reason",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_OFFICER],
        "perms": "wck",
    },
]

_STAGES = [
    ("Initial Qualification", 10, False),
    ("First Interview", 20, False),
    ("Second Interview", 30, False),
    ("Contract Proposal", 40, False),
    ("Contract Signed", 50, True),
]

_SOURCES = [
    ("LinkedIn", False),
    ("Website", False),
    ("Employee Referral", True),
    ("Agency", False),
    ("Other", False),
]

_REASONS = [
    "Not enough experience",
    "Salary expectations",
    "Position filled",
    "Candidate withdrew",
    "Other",
]


async def seed_recruitment_area(env: Any) -> None:
    async with env.dml_conn() as conn:
        has = await conn.execute(text("SELECT 1 FROM hr_recruitment_stage LIMIT 1"))
        if has.fetchone():
            _log.info("hr: recruitment config already seeded; skipping")
            return

    from dodoo.addons.hr.models.hr_applicant_refuse_reason import HrApplicantRefuseReason
    from dodoo.addons.hr.models.hr_recruitment_source import HrRecruitmentSource
    from dodoo.addons.hr.models.hr_recruitment_stage import HrRecruitmentStage

    for name, seq, hired in _STAGES:
        await HrRecruitmentStage.create(
            env, {"name": name, "sequence": seq, "is_hired_stage": hired}
        )
    for name, ref in _SOURCES:
        await HrRecruitmentSource.create(env, {"name": name, "is_referral": ref})
    for name in _REASONS:
        await HrApplicantRefuseReason.create(env, {"name": name})
    _log.info("hr: seeded P3 recruitment config (stages, sources, refuse reasons)")


seed.IR_MODELS.extend(_MODELS)
seed.INDEXES.extend(_INDEXES)
seed.AREA_SEEDS.append(seed_recruitment_area)
rules.HR_RULES.extend(_RULES)
