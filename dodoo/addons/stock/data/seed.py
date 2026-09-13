"""``seed_stock_data`` — the Inventory addon's ``post_install`` entry point.

Order: schema extension (`tracking` column on `product_product`) → ``ir_model`` rows → groups →
indexes → sample data (default warehouse) → record rules. Idempotent.
"""

from __future__ import annotations

import logging
from typing import Any

from dodoo.addons.stock.data import groups, rules
from dodoo.addons.stock.data.indexes import ensure_indexes
from dodoo.addons.stock.data.ir_model_sync import sync_ir_model
from dodoo.addons.stock.data.product_product_ext import add_tracking_column

_log = logging.getLogger(__name__)

IR_MODELS: list[tuple[str, str]] = [
    ("stock.warehouse", "stock_warehouse"),
    ("stock.location", "stock_location"),
    ("stock.picking.type", "stock_picking_type"),
    ("stock.picking", "stock_picking"),
    ("stock.move", "stock_move"),
    ("stock.move.line", "stock_move_line"),
    ("stock.quant", "stock_quant"),
    ("stock.inventory.adjustment.log", "stock_inventory_adjustment_log"),
    ("stock.lot", "stock_lot"),
    ("stock.quant.package", "stock_quant_package"),
    ("stock.package.type", "stock_package_type"),
    ("stock.storage.category", "stock_storage_category"),
    ("stock.putaway.rule", "stock_putaway_rule"),
    ("stock.route", "stock_route"),
    ("stock.rule", "stock_rule"),
    ("stock.warehouse.orderpoint", "stock_warehouse_orderpoint"),
    ("stock.scrap", "stock_scrap"),
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_stock_location_parent ON stock_location (parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_location_warehouse_usage ON stock_location (warehouse_id, usage)",
    "CREATE INDEX IF NOT EXISTS idx_stock_move_picking ON stock_move (picking_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_move_product_state ON stock_move (product_id, state)",
    "CREATE INDEX IF NOT EXISTS idx_stock_move_line_move ON stock_move_line (move_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quant_key ON stock_quant (product_id, location_id, COALESCE(lot_id, 0), COALESCE(package_id, 0))",
    "CREATE INDEX IF NOT EXISTS idx_stock_quant_product ON stock_quant (product_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_lot_product_name ON stock_lot (product_id, name)",
    "CREATE INDEX IF NOT EXISTS idx_stock_orderpoint_product ON stock_warehouse_orderpoint (product_id, location_id)",
]


async def _seed_sample_data(env: Any) -> None:
    from dodoo.addons.stock.models.stock_warehouse import StockWarehouse
    from sqlalchemy import text

    existing = await StockWarehouse.search(env, [["code", "=", "WH"]])
    if existing:
        _log.info("stock: sample warehouse already seeded; skipping")
        return

    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_company LIMIT 1"))
        r = row.fetchone()
    if not r:
        _log.warning("stock: no company found; skipping warehouse seed")
        return
    company_id = r[0]

    await StockWarehouse.create(
        env,
        {
            "name": "Main Warehouse",
            "code": "WH",
            "company_id": company_id,
        },
    )


async def seed_stock_data(env: Any) -> None:
    await add_tracking_column(env)
    await sync_ir_model(env, IR_MODELS)
    await groups.seed(env)
    await ensure_indexes(env, INDEXES)
    await _seed_sample_data(env)
    await rules.apply(env)
    _log.info(
        "stock: seed complete (%d models, %d indexes)", len(IR_MODELS), len(INDEXES)
    )
