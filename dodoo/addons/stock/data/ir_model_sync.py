"""Re-exports `product`'s `sync_ir_model` (stock depends on product; mirrors
`fleet/data/ir_model_sync.py` importing the `hr` helper)."""

from dodoo.addons.product.data.ir_model_sync import sync_ir_model  # noqa: F401
