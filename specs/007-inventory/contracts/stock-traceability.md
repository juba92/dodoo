# Contract: Lots, Serial Numbers & Packages (US5)

JSON-RPC for CRUD on `stock.lot` / `stock.quant.package` / `stock.package.type`; REST for the
traceability lookup and the package-move action. `require_groups(env, uid, "Inventory User",
"Inventory Manager")` on all mutation routes.

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.lot` | `create` | `{name, product_id, company_id, expiration_date?}` | lot id | unique `(product_id, name)` (FR-044) |
| `stock.lot` / `stock.quant.package` / `stock.package.type` | `read` / `search_read` | standard | — | |

## REST routes

### `GET /stock/traceability/lot/{lot_id}`

Returns every `stock.move`/`stock.move.line` that received, moved, or shipped the lot, in
chronological order (FR-048), including moves where it travelled inside a package (FR-054):
`{lot_id, product_id, events: [{move_id, picking_id, date, location_src_id, location_dest_id, qty, package_id}]}`.

### `GET /stock/traceability/package/{package_id}`

Same shape as above, scoped to a package (FR-054).

### `POST /stock/package/{package_id}/move`

Body: `{location_dest_id: int}`. Generates one Internal Transfer picking moving every quant
currently keyed to the package to `location_dest_id` (FR-052). Returns `{picking_id}`.

## Validation models (`stock/validators.py`)

```text
class LotCreate(Payload):
    name: str; product_id: int; company_id: int; expiration_date: date | None

class PackageMove(Payload):
    location_dest_id: int
```
