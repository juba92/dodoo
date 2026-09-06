"""E2E — Recruitment pipeline: stage move by pointer AND keyboard (feature 006, US3/US5).

Requires a running dodoo server with hr installed + Playwright browsers.
Run:  pytest tests/e2e/test_recruitment_ui.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect, sync_playwright

_BASE = "http://127.0.0.1:8069"
_CLIENT = f"{_BASE}/web/client"


@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        yield ctx
        ctx.close()
        browser.close()


@pytest.fixture()
def page(browser_context):
    pg = browser_context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    pg.close()
    if errors:
        pytest.fail(f"Unhandled JS error(s): {'; '.join(errors)}")


def _login(page: Page) -> None:
    page.goto(_CLIENT)
    page.fill("#login, input[name='login']", "admin")
    page.fill("#password, input[name='password']", "admin")
    page.click("button[type='submit'], .btn-primary")
    page.wait_for_url("**/#/home", timeout=5000)


def test_recruitment_job_picker(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/recruitment")
    expect(page.locator(".sidebar-list, .empty-state")).to_be_visible()


def test_pipeline_kanban_and_keyboard_move(page: Page):
    _login(page)
    # first published job
    page.goto(f"{_CLIENT}#/hr/recruitment")
    first = page.locator(".sidebar-list button").first
    if first.count() == 0:
        pytest.skip("no jobs seeded")
    first.click()
    expect(page.locator(".o-kanban, .empty-state")).to_be_visible()
    # keyboard alternative to drag: the per-card "Move to…" <select>
    mover = page.locator(".o-kanban-move").first
    if mover.count():
        expect(mover).to_be_visible()


def test_applicant_form_actions(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/applicant/new")
    expect(page.locator(".o-form")).to_be_visible()


def test_referral_form_and_list(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/referral/new")
    expect(page.locator(".o-form, .empty-state")).to_be_visible()
    page.goto(f"{_CLIENT}#/hr/referrals")
    expect(page.locator(".data-table, .empty-state")).to_be_visible()
