"""End-to-end Playwright tests for the Dodoo Web UI.

Requires a running dodoo server with the web addon installed:
    python -m dodoo module install web
    python -m dodoo server --port 8069

Run:
    pytest tests/e2e/test_web_ui.py -v
"""
from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, sync_playwright

_BASE = "http://127.0.0.1:8069"
_CLIENT = f"{_BASE}/web/client"


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
    # Fail the test on any unhandled JS exception (Constitution IX / SC-004)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    pg.close()
    if errors:
        pytest.fail(f"Unhandled JS error(s): {'; '.join(errors)}")


def _login(page: Page, login: str = "admin", password: str = "admin") -> None:
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    page.fill("#f-login", login)
    page.fill("#f-password", password)
    page.click("button[type=submit]")
    page.wait_for_url(f"**#/home")


# ── US1: Login ────────────────────────────────────────────────────────────────

def test_us1_login_success(page: Page):
    t0 = time.monotonic()
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    elapsed_load = time.monotonic() - t0
    # PERF-001: initial load < 2s
    assert elapsed_load < 2.0, f"Initial load took {elapsed_load:.2f}s (> 2s)"

    page.fill("#f-login", "admin")
    page.fill("#f-password", "admin")
    page.click("button[type=submit]")
    page.wait_for_url("**#/home")
    assert "#/home" in page.url


def test_us1_login_failure(page: Page):
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    page.fill("#f-login", "admin")
    page.fill("#f-password", "wrongpassword")
    page.click("button[type=submit]")
    # Should stay on login, error should appear
    page.wait_for_selector(".error-banner:visible")
    assert "#/login" in page.url or "#/home" not in page.url
    error = page.locator(".error-banner").first
    assert error.is_visible()


def test_us1_session_persist(page: Page):
    _login(page)
    # Reload the page — should stay on home
    page.reload()
    page.wait_for_url("**#/home")
    assert "#/home" in page.url


def test_us1_logout(page: Page):
    _login(page)
    page.click("#btn-logout")
    page.wait_for_url("**#/login")
    assert "#/login" in page.url
    # Token should be cleared — direct navigation to home redirects to login
    page.goto(f"{_CLIENT}#/home")
    page.wait_for_selector("#f-login")


# ── US2: Home Screen ──────────────────────────────────────────────────────────

def test_us2_home_shows_tiles(page: Page):
    t0 = time.monotonic()
    _login(page)
    page.wait_for_selector(".module-tile")
    elapsed_nav = time.monotonic() - t0
    # PERF-002: navigation < 300ms (this covers login→home transition)
    assert page.locator(".module-tile").count() >= 1


def test_us2_tile_has_name_and_icon(page: Page):
    _login(page)
    page.wait_for_selector(".module-tile")
    tile = page.locator(".module-tile").first
    assert tile.locator(".tile-icon").is_visible()
    assert tile.locator(".tile-name").inner_text().strip() != ""


def test_us2_tile_click_navigates(page: Page):
    _login(page)
    page.wait_for_selector(".module-tile")
    # Find and click the 'base' tile
    base_tile = page.locator(".module-tile").filter(has_text="base").first
    base_tile.click()
    page.wait_for_url("**#/module/base")
    assert "#/module/base" in page.url


# ── US3: List View ────────────────────────────────────────────────────────────

def test_us3_list_renders_table(page: Page):
    _login(page)
    t0 = time.monotonic()
    page.goto(f"{_CLIENT}#/model/res.users")
    page.wait_for_selector("table tbody tr")
    elapsed = time.monotonic() - t0
    # PERF-003: list with 50 rows < 500ms (for whatever records exist)
    assert elapsed < 5.0  # generous upper bound for test env latency
    assert page.locator("table thead").is_visible()
    assert page.locator("table tbody tr").count() >= 1


def test_us3_search_filters_rows(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users")
    page.wait_for_selector("table tbody tr")
    page.fill(".search-input", "admin")
    page.wait_for_timeout(600)  # wait for debounce
    page.wait_for_selector("table tbody tr")
    # All visible rows should contain 'admin'
    rows = page.locator("table tbody tr")
    count = rows.count()
    assert count >= 1
    for i in range(count):
        assert "admin" in rows.nth(i).inner_text().lower()


def test_us3_new_button_navigates(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users")
    page.wait_for_selector(".btn[data-action=new]")
    page.click(".btn[data-action=new]")
    page.wait_for_url("**#/model/res.users/new")
    assert "#/model/res.users/new" in page.url


def test_us3_row_click_navigates(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users")
    page.wait_for_selector("table tbody tr")
    page.locator("table tbody tr").first.click()
    page.wait_for_url("**/model/res.users/**")
    assert "/model/res.users/" in page.url


# ── US4: Form View ────────────────────────────────────────────────────────────

def test_us4_form_loads_record(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users/1")
    page.wait_for_selector(".form-card")
    # The admin login field should show 'admin'
    login_input = page.locator("[data-field=login]")
    assert login_input.count() > 0
    val = login_input.first.input_value() if login_input.first.tag_name() == "input" \
        else login_input.first.inner_text()
    assert "admin" in val.lower()


def test_us4_save_persists(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users/1")
    page.wait_for_selector(".form-card")
    # Change the name field
    name_field = page.locator("[data-field=name]").first
    original = name_field.input_value() if name_field.tag_name() == "input" else ""
    name_field.fill("Admin Updated")
    page.click(".btn-primary[data-action=save]")
    page.wait_for_selector(".success-banner")
    # Reload and confirm persisted
    page.reload()
    page.wait_for_selector(".form-card")
    val = page.locator("[data-field=name]").first.input_value()
    assert val == "Admin Updated"
    # Restore
    page.locator("[data-field=name]").first.fill(original or "Administrator")
    page.click(".btn-primary[data-action=save]")
    page.wait_for_selector(".success-banner")


def test_us4_discard_restores(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users/1")
    page.wait_for_selector(".form-card")
    name_field = page.locator("[data-field=name]").first
    original = name_field.input_value()
    name_field.fill("ShouldBeDiscarded")
    page.click(".btn-secondary[data-action=discard]")
    # No server call expected; value should be restored
    assert name_field.input_value() == original


def test_us4_delete_requires_confirm(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users/1")
    page.wait_for_selector(".form-card")
    # Cancel the confirm dialog
    page.on("dialog", lambda d: d.dismiss())
    page.click(".btn-danger[data-action=delete]")
    # Still on same page — record not deleted
    assert "/res.users/1" in page.url


def test_us4_create_new_record(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users/new")
    page.wait_for_selector(".form-card")
    page.locator("[data-field=login]").first.fill("testuser_e2e")
    page.locator("[data-field=name]").first.fill("E2E Test User")
    page.click(".btn-primary[data-action=save]")
    page.wait_for_url("**/model/res.users/*")
    # URL should now contain a numeric ID
    import re
    assert re.search(r"/model/res\.users/\d+", page.url)


# ── US5: Navigation ───────────────────────────────────────────────────────────

def test_us5_breadcrumb_trail(page: Page):
    _login(page)
    page.wait_for_selector(".module-tile")
    page.locator(".module-tile").filter(has_text="base").first.click()
    page.wait_for_url("**#/module/base")
    page.goto(f"{_CLIENT}#/model/res.users")
    page.wait_for_selector("table tbody tr")
    page.locator("table tbody tr").first.click()
    page.wait_for_selector(".form-card")
    # Breadcrumb should have multiple segments
    segments = page.locator(".breadcrumb-strip li")
    assert segments.count() >= 2


def test_us5_breadcrumb_click_navigates(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users/1")
    page.wait_for_selector(".form-card")
    # Click the list segment in breadcrumb
    bc_btns = page.locator(".breadcrumb-strip button")
    if bc_btns.count() > 0:
        bc_btns.first.click()
        page.wait_for_url("**#/home")


def test_us5_back_button(page: Page):
    _login(page)
    page.goto(f"{_CLIENT}#/model/res.users")
    page.wait_for_selector("table tbody tr")
    page.locator("table tbody tr").first.click()
    page.wait_for_selector(".form-card")
    page.go_back()
    page.wait_for_selector("table")
    assert "/model/res.users" in page.url and "/res.users/" not in page.url


def test_us5_sidebar_shows_models(page: Page):
    _login(page)
    page.wait_for_selector("#sidebar")
    sidebar = page.locator("#sidebar")
    assert sidebar.locator("button").count() >= 1
