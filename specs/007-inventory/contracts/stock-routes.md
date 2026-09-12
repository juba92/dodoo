# Contract: Putaway Rules, Storage Categories, Routes & Reordering Rules (US6)

JSON-RPC for CRUD (all `Inventory Manager`-only per FR-082, except read); REST for the
resolution/preview and replenishment-trigger actions.

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.storage.category` | `create` | `{name, max_weight?, max_packages?, allow_new_product, location_ids}` | id | FR-055 |
| `stock.putaway.rule` | `create` | `{location_src_id, product_id? , category_id?, location_dest_id, sequence}` | id | exactly one of `product_id`/`category_id` (FR-056) |
| `stock.route` / `stock.rule` | `create` / `read` / `write` | standard | — | FR-060/061 |
| `stock.warehouse.orderpoint` | `create` | `{product_id, location_id, product_min_qty, product_max_qty, qty_multiple}` | id | FR-063 |

## REST routes

### `GET /stock/putaway/resolve?product_id=&source_location_id=`

Read-only preview of `resolve_destination` (ADR-031, FR-057) — returns
`{destination_location_id, rule_id: int | None}` without moving anything.

### `POST /stock/orderpoint/run`

Body: `{orderpoint_ids: list[int] | None}` (omit = evaluate all in company scope). Requires
`Inventory Manager` (replenishment is a manager action). Runs `run_reordering` (FR-063a/064/065/066).
Returns `{triggered: [{orderpoint_id, picking_ids: [...]}], skipped_covered: [...], unresolved:
[...]}`.

## Validation models (`stock/validators.py`)

```text
class StorageCategoryCreate(Payload):
    name: str; max_weight: float | None; max_packages: int | None
    allow_new_product: Literal["always","same_product","same_lot"] = "always"
    location_ids: list[int] = []

class PutawayRuleCreate(Payload):
    location_src_id: int; product_id: int | None; category_id: int | None
    location_dest_id: int; sequence: int = 10

    @model_validator(mode="after")
    def one_of_product_or_category(self): ...  # exactly one of product_id/category_id

class OrderpointCreate(Payload):
    product_id: int; location_id: int
    product_min_qty: float = Field(ge=0); product_max_qty: float = Field(ge=0)
    qty_multiple: float = Field(gt=0, default=1.0)

class RunReordering(Payload):
    orderpoint_ids: list[int] | None = None
```
