"""In-memory UI translation catalog.

Catalogs are static per-language JSON files, loaded once at import and merged from **every**
installed addon's own ``data/i18n/*.json`` (ADR-036) — not just this (``localization``) addon's.
Each addon owns and ships the translations for the UI strings *it* introduces (menu labels, its
own field names, its own screens), the same way each addon already owns its own ``data/seed.py``
/ ``data/rules.py``; nothing needs to be added to a file in this addon for a new module's strings
to be translated. ``translate()`` resolves the effective language, then falls back to English,
then to the source string — a missing translation never yields a blank label (FR-008). There is
no database translation model and no in-app editing screen (ADR-007).
"""

from __future__ import annotations

import json
import logging
import pathlib

_log = logging.getLogger(__name__)

_I18N_DIR = pathlib.Path(__file__).parent / "data" / "i18n"
# dodoo/addons/<any addon>/data/i18n/<lang>.json — discovered relative to this addon's own
# location: dodoo/addons/localization/i18n.py -> .parent is dodoo/addons/localization/,
# .parent.parent is dodoo/addons/ (the directory every addon, including this one, lives in).
_ADDONS_DIR = pathlib.Path(__file__).parent.parent

# language code -> {source string: translation}
_CATALOGS: dict[str, dict[str, str]] = {}


def _load() -> None:
    _CATALOGS.clear()
    # 1) This addon's own catalog first (generic web/base chrome + shared strings).
    catalog_dirs = [_I18N_DIR]
    # 2) Every other addon's own `data/i18n/` directory, in a stable (sorted) order so a
    #    string defined by two addons resolves deterministically (first one wins per lang).
    if _ADDONS_DIR.is_dir():
        for addon_dir in sorted(_ADDONS_DIR.iterdir()):
            candidate = addon_dir / "data" / "i18n"
            if candidate.is_dir() and candidate != _I18N_DIR:
                catalog_dirs.append(candidate)

    for i18n_dir in catalog_dirs:
        for path in sorted(i18n_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _log.warning("i18n: failed to parse %s; skipping", path)
                continue
            lang = path.stem
            existing = _CATALOGS.setdefault(lang, {})
            for source, translation in data.items():
                existing.setdefault(source, translation)


_load()


def available_langs() -> list[str]:
    return sorted(_CATALOGS)


def catalog(lang: str) -> dict[str, str]:
    """Full source→translation map for ``lang`` (empty dict if unknown)."""
    return dict(_CATALOGS.get(lang, {}))


def translate(text: str, lang: str) -> str:
    """Translate a static UI string into ``lang`` with EN→source fallback."""
    if not text:
        return text
    hit = _CATALOGS.get(lang, {}).get(text)
    if hit is not None:
        return hit
    en = _CATALOGS.get("en", {}).get(text)
    if en is not None:
        return en
    return text
