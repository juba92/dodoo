"""``stock.inventory.adjustment.log`` — append-only audit trail for applied counts (FR-040)."""

from __future__ import annotations

from dodoo.core.fields import Float, Many2one
from dodoo.core.models import BaseModel


class StockInventoryAdjustmentLog(BaseModel):
    _name = "stock.inventory.adjustment.log"

    product_id = Many2one("product.product", required=True)
    location_id = Many2one("stock.location", required=True)
    lot_id = Many2one("stock.lot")
    qty_before = Float(required=True)
    qty_after = Float(required=True)
    difference = Float(required=True)
    uid = Many2one("res.users")
    move_id = Many2one("stock.move")
