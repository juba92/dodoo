"""``hr.appraisal.template`` + ``hr.appraisal.feedback.section`` (FR-039, ADR-026)."""

from __future__ import annotations

from dodoo.core.fields import Char, Integer, Many2one, Text
from dodoo.core.models import BaseModel


class HrAppraisalTemplate(BaseModel):
    _name = "hr.appraisal.template"

    name = Char(size=64, required=True)
    default_frequency_months = Integer(default=12)
    company_id = Many2one("res.company")


class HrAppraisalFeedbackSection(BaseModel):
    _name = "hr.appraisal.feedback.section"

    template_id = Many2one("hr.appraisal.template", required=True)
    title = Char(size=128, required=True)
    prompt = Text()
    sequence = Integer(default=10)
