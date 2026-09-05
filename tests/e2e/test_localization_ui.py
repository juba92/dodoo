"""End-to-end Playwright tests for Localization & Settings (005).

Requires a running dodoo server with the localization addon installed against a fresh DB:
    python -m dodoo module install localization
    python -m dodoo server --port 8069

Run:
    pytest tests/e2e/test_localization_ui.py -v
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, sync_playwright

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
    page.wait_for_selector("#f-login")
    page.fill("#f-login", "admin")
    page.fill("#f-password", "admin")
    page.click("button[type=submit]")
    page.wait_for_url("**#/home")


def _html_dir(page: Page) -> str:
    return page.evaluate("document.documentElement.getAttribute('dir')")


# ── US1: Arabic RTL on a fresh install, language switch ───────────────────────

def test_fresh_install_login_is_arabic_rtl(page: Page):
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    assert _html_dir(page) == "rtl"
    assert page.evaluate("document.documentElement.getAttribute('lang')") == "ar"
    # login button label is translated
    assert page.locator("button[type=submit]").inner_text().strip() == "تسجيل الدخول"


def test_primary_screens_render_rtl_when_arabic(page: Page):
    _login(page)
    for hash_ in ("#/home", "#/model/res.users", "#/settings"):
        page.goto(_CLIENT + hash_)
        page.wait_for_timeout(200)
        assert _html_dir(page) == "rtl", hash_


def test_admin_switches_system_language_to_english_ltr(page: Page):
    _login(page)
    page.goto(_CLIENT + "#/settings")
    page.wait_for_selector("#set-sys-lang")
    page.select_option("#set-sys-lang", "en")
    page.locator(".settings-actions button", has_text="حفظ").click()
    page.wait_for_function("document.documentElement.getAttribute('dir') === 'ltr'")
    assert _html_dir(page) == "ltr"
    # no re-login required
    assert "#/settings" in page.url


# ── US2: personal language override ──────────────────────────────────────────

def test_personal_language_override_round_trip(page: Page):
    _login(page)
    page.goto(_CLIENT + "#/settings")
    page.wait_for_selector("#set-user-lang")
    page.select_option("#set-user-lang", "en")
    page.locator(".settings-actions button").first.click()
    page.wait_for_function("document.documentElement.getAttribute('dir') === 'ltr'")
    # revert to system default
    page.goto(_CLIENT + "#/settings")
    page.wait_for_selector("#set-user-lang")
    page.select_option("#set-user-lang", "")
    page.locator(".settings-actions button").first.click()
    page.wait_for_function("document.documentElement.getAttribute('dir') === 'rtl'")


# ── US3 / US4: country selection + currency-conflict confirm ─────────────────

def test_country_field_lists_countries_and_shows_derived_config(page: Page):
    _login(page)
    page.goto(_CLIENT + "#/settings")
    page.wait_for_selector("#set-country")
    options = page.locator("#set-country option")
    assert options.count() >= 2
    assert page.locator(".derived").is_visible()


# ── Accessibility ───────────────────────────────────────────────────────────

def test_lang_and_dir_attributes_set_for_assistive_tech(page: Page):
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    assert page.evaluate("document.documentElement.getAttribute('lang')") in ("ar", "en")
    assert _html_dir(page) in ("rtl", "ltr")


def test_language_selector_is_keyboard_navigable(page: Page):
    _login(page)
    page.goto(_CLIENT + "#/settings")
    page.wait_for_selector("#set-user-lang")
    page.focus("#set-user-lang")
    assert page.evaluate("document.activeElement.id") == "set-user-lang"
