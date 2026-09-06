"""Human Resources addon.

Reproduces the behaviour of the Odoo 19.0 Human Resources application section:
Employees + org structure + tags, Contracts, Skills, Time Off, Recruitment, Appraisals,
and Referrals. Fleet is a separate addon (``dodoo/addons/fleet/``) that depends on this one.

Built on the dodoo stack (FastAPI routing, SQLAlchemy Core async ``BaseModel``, Pydantic v2
whitelist validation at the HTTP boundary, ``ir.rule`` record rules, the vanilla-JS SPA) and
the patterns established in 001-erp-core / 002-web-ui / 005-localization-settings. Wages are
plain ``Monetary`` amounts in the company currency — no dependency on the ``account`` addon.
"""

from dodoo.addons.hr import http, models  # noqa: F401


async def post_install(env):
    from dodoo.addons.hr.data.seed import seed_hr_data

    await seed_hr_data(env)
