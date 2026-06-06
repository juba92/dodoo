"""Accessibility e2e tests using axe-playwright.

Requires:
    pip install axe-playwright
    playwright install chromium

Run:
    pytest tests/e2e/test_web_ui_a11y.py -v
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, sync_playwright

_BASE = "http://127.0.0.1:8069"
_CLIENT = f"{_BASE}/web/client"


@pytest.fixture(scope="session")
def a11y_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture()
def a11y_page(a11y_browser):
    ctx = a11y_browser.new_context()
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: pytest.fail(f"Unhandled JS error: {e}"))
    yield pg
    pg.close()
    ctx.close()


def _login(page: Page) -> None:
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    page.fill("#f-login", "admin")
    page.fill("#f-password", "admin")
    page.click("button[type=submit]")
    page.wait_for_url("**#/home")


def _run_axe(page: Page) -> list[dict]:
    """Inject axe-core and return violations."""
    page.add_script_tag(
        url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.0/axe.min.js"
    )
    results = page.evaluate("""
        () => new Promise(resolve =>
            axe.run({ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } })
               .then(r => resolve(r.violations))
        )
    """)
    return results


def test_a11y_login(a11y_page: Page):
    a11y_page.goto(_CLIENT)
    a11y_page.wait_for_selector("#f-login")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        f"WCAG 2.1 AA critical violations on login screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_home(a11y_page: Page):
    _login(a11y_page)
    a11y_page.wait_for_selector(".module-tile")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        f"WCAG 2.1 AA critical violations on home screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/res.users")
    a11y_page.wait_for_selector("table")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        f"WCAG 2.1 AA critical violations on list screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_form(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/res.users/1")
    a11y_page.wait_for_selector(".form-card")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        f"WCAG 2.1 AA critical violations on form screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )
