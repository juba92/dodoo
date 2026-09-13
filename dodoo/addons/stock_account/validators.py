"""Re-exports the whitelist-validation helpers from `stock` (stock_account depends on stock,
mirrors `fleet/validators.py` re-exporting from `hr`), plus stock_account-specific payloads."""

from __future__ import annotations

from typing import Literal

from dodoo.addons.stock.validators import (  # noqa: F401
    Payload,
    and_domain,
    group_names,
    is_member,
    require_groups,
    validate,
)


class CategoryValuationConfig(Payload):
    costing_method: Literal["standard", "average", "fifo"] = "standard"
    property_stock_valuation_account_id: int
    property_stock_input_account_id: int
    property_stock_output_account_id: int
