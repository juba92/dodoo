# Contract: Transfers & Stock Moves — Receipts, Deliveries, Internal, Returns (US3)

JSON-RPC `execute_kw` for creating/reading a `stock.picking` and its `stock.move` lines; REST
actions for every workflow verb (confirm/reserve/validate/cancel/return), each requiring
`require_groups(env, uid, "Inventory User", "Inventory Manager")` (FR-081) and each re-checking the
record's state server-side (FR-035, ADR-030) before applying.

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.picking` | `create` | `{picking_type_id, partner_id?, scheduled_date, moves: [{product_id, product_uom_qty, product_uom_id, location_src_id?, location_dest_id?}]}` | picking id | moves default their locations from the operation type (FR-024) |
| `stock.picking` / `stock.move` | `read` / `search_read` | standard | — | `state` on the picking is derived (ADR-030), read-only |
| `stock.move.line` | `write` | `{qty_done, lot_id?, package_id?, result_package_id?}` | `True` | used while preparing a transfer for validation |

## REST routes

### `POST /stock/picking/{picking_id}/confirm`

Confirms the picking: attempts reservation on each move (`FOR UPDATE`, D2), moves to `waiting` or
`ready` (FR-025). Body: `{}`. Returns `{state, moves: [{move_id, state, reserved_qty}]}`.

### `POST /stock/picking/{picking_id}/validate`

Body: `TransferValidate {expected_state: str, create_backorder: bool | None}`. Rejects with a
conflict error if the picking's derived state no longer matches `expected_state` (FR-035). Writes
move-line `qty_done`, updates `stock.quant` at source/destination, sets moves `done`. If reserved <
demanded and the operation type's `backorder_policy` is `ask`, `create_backorder` selects whether a
backorder picking is created for the remainder (FR-028); `always`/`never` ignore the flag. Returns
`{state, backorder_id: int | None}`.

### `POST /stock/picking/{picking_id}/cancel`

Body: `{expected_state: str}`. Releases reservations, sets moves `cancelled` (FR-031). `409` if a
move is already `done`.

### `POST /stock/picking/{picking_id}/return`

Body: `{}`. Creates a new picking on the Returns-configured operation type mirroring the original's
moved quantities with source/destination swapped (FR-030). Returns `{return_picking_id}`.

### `GET /stock/product/{product_id}/forecast?location_id=`

Returns `{on_hand, reserved, incoming, outgoing, forecasted}` (FR-011/034).

## Validation models (`stock/validators.py`)

```text
class TransferCreate(Payload):
    picking_type_id: int; partner_id: int | None; scheduled_date: datetime | None
    moves: list[MoveSpec]   # MoveSpec = {product_id, product_uom_qty: float (gt=0), product_uom_id,
                             #             location_src_id: int | None, location_dest_id: int | None}

class TransferValidate(Payload):
    expected_state: Literal["draft","waiting","confirmed","ready"]
    create_backorder: bool | None = None

class TransferCancel(Payload):
    expected_state: Literal["draft","waiting","confirmed","ready"]

class MoveLineUpdate(Payload):
    qty_done: float = Field(ge=0); lot_id: int | None; package_id: int | None; result_package_id: int | None
```
