"""Re-exports `product`'s `ensure_indexes` helper."""

from dodoo.addons.product.data.indexes import ensure_indexes  # noqa: F401

# PERF-004: FIFO's "open layers" query never scans consumed layers.
INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_svl_product_remaining ON stock_valuation_layer (product_id) WHERE remaining_qty <> 0",
    "CREATE INDEX IF NOT EXISTS idx_svl_move ON stock_valuation_layer (stock_move_id)",
]
