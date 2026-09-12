# Contract: Scrap (US7)

JSON-RPC create/read; one REST action for confirmation. `require_groups(env, uid, "Inventory
User", "Inventory Manager")`.

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.scrap` | `create` | `{product_id, lot_id?, quantity, location_src_id, location_dest_id}` | id | starts `draft` (FR-067) |
| `stock.scrap` | `read` / `search_read` | standard | — | a `done` record is read-only (FR-069) |

## REST routes

### `POST /stock/scrap/{scrap_id}/confirm`

Body: `{}`. Rejects if `quantity` exceeds available on-hand at `location_src_id` (FR-068). On
success: creates the underlying `stock.move`, updates on-hand, sets `state = done`. Returns
`{state, move_id}`.

## Validation models (`stock/validators.py`)

```text
class ScrapCreate(Payload):
    product_id: int; lot_id: int | None; quantity: float = Field(gt=0)
    location_src_id: int; location_dest_id: int; reason: str | None = Field(default=None, max_length=256)
```
