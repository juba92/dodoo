"""P3 area — Appraisals (templates, feedback sections + rows, appraisal cycle)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from dodoo.addons.hr.data import rules, seed
from dodoo.addons.hr.security import GROUP_EMPLOYEE

_log = logging.getLogger(__name__)

_MODELS = [
    ("hr.appraisal.template", "hr_appraisal_template"),
    ("hr.appraisal.feedback.section", "hr_appraisal_feedback_section"),
    ("hr.appraisal.feedback", "hr_appraisal_feedback"),
    ("hr.appraisal", "hr_appraisal"),
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hr_appraisal_employee_state "
    "ON hr_appraisal (employee_id, state)",
    "CREATE INDEX IF NOT EXISTS idx_hr_appraisal_company ON hr_appraisal (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_appraisal_feedback_appraisal "
    "ON hr_appraisal_feedback (appraisal_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_appraisal_feedback_section_template "
    "ON hr_appraisal_feedback_section (template_id)",
]

_RULES = [
    # hr.appraisal — appraisee OR their manager (Employee group); Officer/Administrator full.
    {
        "name": "hr.appraisal: own or team (Employee)",
        "model": "hr.appraisal",
        "domain": [
            "&",
            ["company_id", "in", "$company_ids"],
            "|",
            ["employee_id.user_id", "=", "$uid"],
            ["employee_id.manager_id.user_id", "=", "$uid"],
        ],
        "groups": [GROUP_EMPLOYEE],
        "perms": "r",
    },
    rules.officer_full("hr.appraisal"),
    rules.deny_all("hr.appraisal"),
    # hr.appraisal.feedback — visibility is filtered in the model layer; the rule only
    # scopes to appraisals the caller can see (own or team), plus Officer full.
    {
        "name": "hr.appraisal.feedback: own or team (Employee)",
        "model": "hr.appraisal.feedback",
        "domain": [
            "|",
            ["appraisal_id.employee_id.user_id", "=", "$uid"],
            ["appraisal_id.employee_id.manager_id.user_id", "=", "$uid"],
        ],
        "groups": [GROUP_EMPLOYEE],
        "perms": "rw",
    },
    rules.officer_full("hr.appraisal.feedback"),
    rules.deny_all("hr.appraisal.feedback"),
    # templates + sections — catalog
    rules.catalog_read("hr.appraisal.template"),
    rules.catalog_admin_write("hr.appraisal.template"),
    {
        "name": "hr.appraisal.feedback.section: read (HR)",
        "model": "hr.appraisal.feedback.section",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_EMPLOYEE],
        "perms": "r",
    },
    {
        "name": "hr.appraisal.feedback.section: write (Administrator)",
        "model": "hr.appraisal.feedback.section",
        "domain": [[1, "=", 1]],
        "groups": ["HR Administrator"],
        "perms": "wck",
    },
]

_SECTIONS = [
    ("Achievements", "What went well this period?"),
    ("Areas for improvement", "What could have gone better?"),
    ("Goals for next period", "What are the priorities going forward?"),
]


async def seed_appraisal_area(env: Any) -> None:
    async with env.dml_conn() as conn:
        has = await conn.execute(text("SELECT 1 FROM hr_appraisal_template LIMIT 1"))
        if has.fetchone():
            _log.info("hr: appraisal template already seeded; skipping")
            return

    from dodoo.addons.hr.models.hr_appraisal_template import (
        HrAppraisalFeedbackSection,
        HrAppraisalTemplate,
    )

    tid = await HrAppraisalTemplate.create(
        env, {"name": "Annual Review", "default_frequency_months": 12}
    )
    for i, (title, prompt) in enumerate(_SECTIONS):
        await HrAppraisalFeedbackSection.create(
            env,
            {"template_id": tid, "title": title, "prompt": prompt, "sequence": i * 10},
        )
    _log.info("hr: seeded P3 appraisal template (Annual Review, 3 sections)")


seed.IR_MODELS.extend(_MODELS)
seed.INDEXES.extend(_INDEXES)
seed.AREA_SEEDS.append(seed_appraisal_area)
rules.HR_RULES.extend(_RULES)
