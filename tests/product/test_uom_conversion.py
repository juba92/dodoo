"""US1 — unit-of-measure conversion math (FR-002/003)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def _uoms(env):
    from dodoo.addons.product.models.uom import UomCategory, UomUom

    length = await UomCategory.create(env, {"name": "Length Test"})
    weight = await UomCategory.create(env, {"name": "Weight Test"})
    m = await UomUom.create(
        env, {"name": "Meter Test", "category_id": length, "uom_type": "reference", "ratio": 1.0}
    )
    cm = await UomUom.create(
        env, {"name": "Centimeter Test", "category_id": length, "uom_type": "smaller", "ratio": 0.01}
    )
    kg = await UomUom.create(
        env, {"name": "Kilogram Test", "category_id": weight, "uom_type": "reference", "ratio": 1.0}
    )
    return {"m": m, "cm": cm, "kg": kg}


async def test_convert_smaller_to_reference(env, _uoms):
    from dodoo.addons.product.models.uom import UomUom

    result = await UomUom.convert(env, 250, _uoms["cm"], _uoms["m"])
    assert result == pytest.approx(2.5)


async def test_convert_reference_to_smaller(env, _uoms):
    from dodoo.addons.product.models.uom import UomUom

    result = await UomUom.convert(env, 2.5, _uoms["m"], _uoms["cm"])
    assert result == pytest.approx(250)


async def test_convert_rejects_cross_category(env, _uoms):
    from dodoo.addons.product.models.uom import UomUom

    with pytest.raises(DodooError, match="uom_category_mismatch"):
        await UomUom.convert(env, 1, _uoms["m"], _uoms["kg"])


async def test_second_reference_in_same_category_rejected(env, _uoms):
    from dodoo.addons.product.models.uom import UomUom

    length_category = (await UomUom.read(env, [_uoms["m"]], ["category_id"]))[0]["category_id"]
    with pytest.raises(DodooError, match="uom_reference_exists"):
        await UomUom.create(
            env,
            {
                "name": "Foot Test",
                "category_id": length_category,
                "uom_type": "reference",
                "ratio": 1.0,
            },
        )
