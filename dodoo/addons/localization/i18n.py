"""In-memory UI translation catalog.

Catalogs are static per-language JSON files shipped with this addon and loaded once at
import. ``translate()`` resolves the effective language, then falls back to English, then
to the source string — a missing translation never yields a blank label (FR-008). There is
no database translation model and no in-app editing screen (ADR-007).
"""

from __future__ import annotations

import json
import pathlib

_I18N_DIR = pathlib.Path(__file__).parent / "data" / "i18n"

# language code -> {source string: translation}
_CATALOGS: dict[str, dict[str, str]] = {}


def _load() -> None:
    for path in sorted(_I18N_DIR.glob("*.json")):
        try:
            _CATALOGS[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CATALOGS[path.stem] = {}


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
