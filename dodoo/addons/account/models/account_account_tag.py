from __future__ import annotations

from dodoo.core.fields import Char, Many2one, Selection
from dodoo.core.models import BaseModel

TAG_APPLICABILITY_CHOICES = [
    ("taxes", "Taxes"),
]


class AccountAccountTag(BaseModel):
    """A tax-grid label (FR-016) — attached to tax repartition lines' ``tag_ids``.

    Only tax-repartition tagging is in scope for this feature (``applicability`` is fixed
    to ``"taxes"``); G/L-account tagging is not modelled.
    """

    _name = "account.account.tag"

    name = Char(size=128, required=True)
    applicability = Selection(TAG_APPLICABILITY_CHOICES, default="taxes")
    country_id = Many2one("res.country")
