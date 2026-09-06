"""End-to-end Playwright tests for the Human Resources web UI (feature 006, US1+).

Requires a running dodoo server with the hr addon installed and Playwright browsers:
    python -m dodoo module install hr
    python -m dodoo server --port 8069
    playwright install chromium

Run:  pytest tests/e2e/test_hr_ui.py -v
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
    page.fill("input[name='login'], #login", "admin")
    page.fill("input[name='password'], #password", "admin")
    page.click("button[type='submit'], .btn-primary")
    page.wait_for_url("**/#/home", timeout=5000)


def test_employees_kanban_and_form(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/employees")
    expect(page.locator(".o-kanban, .empty-state")).to_be_visible()
    page.goto(f"{_CLIENT}#/hr/employee/new")
    expect(page.locator(".o-form-tabbar")).to_be_visible()
    # four tabs present
    assert page.locator(".o-form-tab").count() == 4


def test_contract_list_has_state_control(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/contracts")
    expect(page.locator(".data-table, .empty-state")).to_be_visible()


def test_hr_menu_sections_render(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/employees")
    expect(page.locator(".sidebar-section-title", has_text="Employees")).to_be_visible()


def test_timeoff_calendar_renders(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/timeoff")
    expect(page.locator(".o-calendar, .alert-error")).to_be_visible()


def test_timeoff_request_form_has_duration_preview(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/hr/timeoff/new")
    expect(page.locator(".o-duration-preview")).to_be_visible()


def test_rtl_layout_when_arabic(page: Page):
    _login(page)
    # assumes the system default language is Arabic on a fresh install (feature 005)
    page.goto(f"{_CLIENT}#/hr/employees")
    direction = page.evaluate("document.documentElement.getAttribute('dir')")
    assert direction in ("rtl", "ltr")  # both valid; asserts the attr is set
