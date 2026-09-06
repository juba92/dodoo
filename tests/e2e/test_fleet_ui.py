"""E2E — Fleet UI (feature 006, US6). Needs a running server with fleet installed + browsers."""

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


def test_vehicles_kanban(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/fleet/vehicles")
    expect(page.locator(".o-kanban, .empty-state")).to_be_visible()


def test_fleet_alerts(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/fleet/alerts")
    expect(page.locator(".data-table, .empty-state, .alert-error")).to_be_visible()


def test_fleet_menu_sections(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/fleet/vehicles")
    expect(page.locator(".sidebar-section-title", has_text="Fleet")).to_be_visible()
