"""Fleet HTTP-boundary whitelist validators — re-uses the ``hr`` helpers."""

from __future__ import annotations

from dodoo.addons.hr.validators import (  # noqa: F401
    Payload,
    group_names,
    is_member,
    require_groups,
    validate,
)
