"""Unit tests for the in-memory translation catalog (no DB)."""
from __future__ import annotations

from dodoo.addons.localization import i18n


def test_catalogs_loaded():
    langs = i18n.available_langs()
    assert "en" in langs and "ar" in langs


def test_translate_hit_arabic():
    assert i18n.translate("Settings", "ar") == "الإعدادات"
    assert i18n.translate("Home", "ar") == "الرئيسية"


def test_translate_falls_back_to_english_source_when_missing():
    # A key absent from ar.json resolves to the English source string, never blank.
    missing = "___definitely_not_a_key___"
    assert i18n.translate(missing, "ar") == missing


def test_translate_unknown_language_falls_back_to_english():
    assert i18n.translate("Save", "fr") == "Save"


def test_translate_empty_is_passthrough():
    assert i18n.translate("", "ar") == ""


def test_catalog_returns_copy():
    c = i18n.catalog("en")
    c["Home"] = "mutated"
    assert i18n.catalog("en")["Home"] == "Home"


def test_placeholder_keys_present_for_currency_conflict_dialog():
    key = (
        "Changing the country will change the functional currency from {from} to {to}. "
        "{posted_lines} posted accounting line(s) exist. Continue?"
    )
    assert key in i18n.catalog("en")
    assert key in i18n.catalog("ar")
