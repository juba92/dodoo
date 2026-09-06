"""P3 area — Referrals (employee refers a candidate to a published job)."""

from __future__ import annotations

from dodoo.addons.hr.data import rules, seed
from dodoo.addons.hr.security import GROUP_EMPLOYEE

_MODELS = [("hr.referral", "hr_referral")]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hr_referral_referrer ON hr_referral (referrer_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_referral_job ON hr_referral (job_id)",
]

_RULES = [
    {
        "name": "hr.referral: own (Employee)",
        "model": "hr.referral",
        "domain": [
            "&",
            ["company_id", "in", "$company_ids"],
            ["referrer_id.user_id", "=", "$uid"],
        ],
        "groups": [GROUP_EMPLOYEE],
        "perms": "rc",
    },
    rules.officer_full("hr.referral"),
    rules.deny_all("hr.referral"),
]

seed.IR_MODELS.extend(_MODELS)
seed.INDEXES.extend(_INDEXES)
rules.HR_RULES.extend(_RULES)
