from dodoo.addons.localization.packs.egypt import EGYPT_PACK

PACKS = {"EG": EGYPT_PACK}


def get_pack(country_code: str):
    """Return the localization package for an ISO country code, or None."""
    return PACKS.get((country_code or "").upper())
