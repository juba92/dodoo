# Contract: Warehouses, Locations & Operation Types (US2)

JSON-RPC `execute_kw` for plain CRUD on `stock.warehouse` / `stock.location` /
`stock.picking.type`; REST actions for the step-configuration side effect. Every mutation route
requires `require_groups(env, uid, "Inventory Manager")` (FR-082) — Location/Operation-Type
configuration is a Manager-only capability; `Inventory User` has read-only access (FR-081).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.warehouse` | `create` | `{name, code, company_id, address, reception_steps, delivery_steps}` | warehouse id | triggers `action_apply_steps` (ADR-029) after insert |
| `stock.warehouse` | `write` | `{reception_steps?, delivery_steps?, ...}` | `True` | re-running `action_apply_steps` on a steps change |
| `stock.warehouse` / `stock.location` / `stock.picking.type` | `read` / `search_read` | standard | — | company-scoped via `ir.rule` |
| `stock.location` | `create` | `{name, parent_id, usage, warehouse_id?}` | location id | FR-015 |

## REST routes

### `GET /stock/warehouse/{warehouse_id}/topology`

Returns the warehouse's location hierarchy and operation types together (FR-021):
`{locations: [{id, name, usage, parent_id}], picking_types: [{id, name, code, default_location_src_id, default_location_dest_id}]}`.

### `POST /stock/warehouse/{warehouse_id}/apply-steps`

Re-runs `action_apply_steps` explicitly (idempotent — safe to call after a direct `write` on the
steps fields too, as a manual "repair topology" action). `403` unless `Inventory Manager`. Returns
`{created_locations: [...], created_picking_types: [...], archived_locations: [...]}` (D4).

## Validation models (`stock/validators.py`)

```text
class WarehouseCreate(Payload):
    name: str; code: str = Field(max_length=16); company_id: int; address: str | None
    reception_steps: Literal["one_step","two_steps","three_steps"] = "one_step"
    delivery_steps: Literal["one_step","two_steps","three_steps"] = "one_step"

class LocationCreate(Payload):
    name: str; parent_id: int | None
    usage: Literal["internal","customer","vendor","inventory","production","transit","view"]
    warehouse_id: int | None  # required when usage == "internal"

class PickingTypeCreate(Payload):
    name: str; code: Literal["incoming","outgoing","internal"]; warehouse_id: int
    default_location_src_id: int | None; default_location_dest_id: int | None
    reservation_mode: Literal["immediate","manual"] = "immediate"
    backorder_policy: Literal["ask","always","never"] = "ask"
```
