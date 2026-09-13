"""``stock.picking.type`` — a named kind of transfer (FR-017/018)."""

from __future__ import annotations

from dodoo.core.fields import Char, Many2one, Selection
from dodoo.core.models import BaseModel

CODE_CHOICES = [
    ("incoming", "Incoming"),
    ("outgoing", "Outgoing"),
    ("internal", "Internal"),
]

RESERVATION_MODE_CHOICES = [
    ("immediate", "Immediate"),
    ("manual", "Manual"),
]

BACKORDER_POLICY_CHOICES = [
    ("ask", "Ask"),
    ("always", "Always"),
    ("never", "Never"),
]


class StockPickingType(BaseModel):
    _name = "stock.picking.type"

    name = Char(size=128, required=True)
    code = Selection(CODE_CHOICES, required=True)
    warehouse_id = Many2one("stock.warehouse", required=True)
    default_location_src_id = Many2one("stock.location")
    default_location_dest_id = Many2one("stock.location")
    sequence_prefix = Char(size=16)
    reservation_mode = Selection(RESERVATION_MODE_CHOICES, default="immediate")
    backorder_policy = Selection(BACKORDER_POLICY_CHOICES, default="ask")
