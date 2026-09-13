"""Every stock table (and the tracking extension column) exists after install (data-model.md)."""

from __future__ import annotations

from sqlalchemy import text

_TABLES = [
    "stock_warehouse",
    "stock_location",
    "stock_picking_type",
    "stock_picking",
    "stock_move",
    "stock_move_line",
    "stock_quant",
    "stock_inventory_adjustment_log",
    "stock_lot",
    "stock_quant_package",
    "stock_package_type",
    "stock_storage_category",
    "stock_putaway_rule",
    "stock_route",
    "stock_rule",
    "stock_warehouse_orderpoint",
    "stock_scrap",
]


async def test_all_tables_exist(env):
    async with env.dml_conn() as conn:
        for table in _TABLES:
            row = await conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
                {"t": table},
            )
            assert row.fetchone() is not None, f"missing table {table}"


async def test_tracking_column_exists_on_product_product(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'product_product' AND column_name = 'tracking'"
            )
        )
        assert row.fetchone() is not None
