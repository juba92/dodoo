"""Regression guard for ADR-036: every label an addon can render must be translatable.

This is the automated backstop for the failure that shipped, unnoticed, with `hr`, `fleet`, and
`stock`: a menu label or field label introduced by an addon with no entry in *any* addon's
`data/i18n/{lang}.json` silently falls back to English (by design, per FR-008) instead of failing
loudly. That silence is exactly why the bug reached production three times before ADR-036. These
tests make the gap loud again by asserting, for every installed addon, that every field label
(``field.string`` or its humanized fallback — the same computation `fields_get` uses) and every
sidebar menu/section label is present in the merged English *and* Arabic catalogs.

A new addon that ships UI-facing strings without a `data/i18n/{en,ar}.json` entry for them will
fail here — that is the point. See ADR-036 and `docs/adr/036-per-addon-i18n-catalogs.md`.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from dodoo.addons.localization import i18n
from dodoo.core.models import _ALL_MODELS, _humanize

_ADDONS_DIR = Path(__file__).parent.parent.parent / "dodoo" / "addons"
_MENU_LABEL_RE = re.compile(r"(?:label|section)\s*:\s*'((?:[^'\\]|\\.)*)'")


def _import_all_addons() -> None:
    for pkg_dir in sorted(_ADDONS_DIR.iterdir()):
        if pkg_dir.is_dir() and (pkg_dir / "__manifest__.py").exists():
            importlib.import_module(f"dodoo.addons.{pkg_dir.name}")


_import_all_addons()

# Reflects the exact label i18n._load() would produce after importing every addon above,
# independent of import order in this test run.
i18n._load()

_EN = i18n.catalog("en")
_AR = i18n.catalog("ar")


def _model_field_labels() -> list[tuple[str, str]]:
    """[(model.field, label)] for every field on every registered model, deduplicated by label.

    Restricted to real addon models (``dodoo.addons.<addon>.models...``) — the test suite itself
    registers throwaway fixture models (``test.company``, ``bench.model``, ...) via the same
    ``_ModelMeta`` registry for unrelated ORM/perf tests, and those never ship an i18n catalog.
    """
    seen: dict[str, str] = {}
    for model in _ALL_MODELS:
        if not model.__module__.startswith("dodoo.addons.") or ".models" not in model.__module__:
            continue
        fields = getattr(model, "_fields", {})
        for fname, field in fields.items():
            label = field.string or _humanize(fname)
            seen.setdefault(label, f"{getattr(model, '_name', model.__name__)}.{fname}")
    return sorted(seen.items(), key=lambda kv: kv[1])


def _menu_labels() -> list[tuple[str, str]]:
    """[(label, source file)] for every `label`/`section` string in a `*-menu.js` file."""
    out = []
    for menu_file in sorted(_ADDONS_DIR.glob("*/static/*-menu.js")):
        text = menu_file.read_text(encoding="utf-8")
        for label in _MENU_LABEL_RE.findall(text):
            out.append((label, str(menu_file.relative_to(_ADDONS_DIR.parent.parent))))
    return out


@pytest.mark.parametrize("label,source", _model_field_labels())
def test_field_label_has_english_catalog_entry(label, source):
    assert label in _EN, (
        f"{source}: field label {label!r} has no entry in any addon's data/i18n/en.json — "
        "add one to the owning addon's catalog (ADR-036)."
    )


@pytest.mark.parametrize("label,source", _model_field_labels())
def test_field_label_has_arabic_catalog_entry(label, source):
    assert label in _AR, (
        f"{source}: field label {label!r} has no Arabic translation in any addon's "
        "data/i18n/ar.json — it will silently render in English with the UI set to Arabic "
        "(ADR-036)."
    )


@pytest.mark.parametrize("label,source", _menu_labels())
def test_menu_label_has_english_catalog_entry(label, source):
    assert label in _EN, (
        f"{source}: menu label {label!r} has no entry in any addon's data/i18n/en.json (ADR-036)."
    )


@pytest.mark.parametrize("label,source", _menu_labels())
def test_menu_label_has_arabic_catalog_entry(label, source):
    assert label in _AR, (
        f"{source}: menu label {label!r} has no Arabic translation in any addon's "
        "data/i18n/ar.json — it will silently render in English with the UI set to Arabic "
        "(ADR-036)."
    )
