# Contract: Physical Inventory Adjustments (US4)

REST-only (a count is a filtered view over `stock.quant`, not a standalone model a client would
create via JSON-RPC). `require_groups(env, uid, "Inventory User", "Inventory Manager")` on both
routes (FR-081).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.quant` | `search_read` | `domain: [["location_id","=",...], ["product_id.category_id","=",...]]` | quant rows incl. `counted_quantity` | used by the client to render the count grid (FR-037) |
| `stock.inventory.adjustment.log` | `search_read` | standard | — | FR-040/042 history view |

## REST routes

### `POST /stock/inventory/count/set`

Body: `CountSet {lines: [{quant_id, counted_quantity}]}` — stages counted quantities without
applying them yet (lets a count be paused/resumed). Returns `{updated: int}`.

### `POST /stock/inventory/count/apply`

Body: `CountApply {quant_ids: list[int]}`. For each quant whose `counted_quantity` differs from
`quantity`, creates the adjustment move + `stock.inventory.adjustment.log` row and updates on-hand
(FR-038); quants where they match are skipped with no move created (FR-039). Returns
`{applied: int, skipped: int, log_ids: list[int]}`.

## Validation models (`stock/validators.py`)

```text
class CountSet(Payload):
    lines: list[CountLine]   # CountLine = {quant_id: int, counted_quantity: float (ge=0)}

class CountApply(Payload):
    quant_ids: list[int]
```
