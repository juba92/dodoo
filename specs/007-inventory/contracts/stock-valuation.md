# Contract: Inventory Valuation & Accounting Integration (US8)

Lives in `dodoo/addons/stock_account/`. Valuation layers and journal entries are never created via
a direct user-facing mutation endpoint (FR-084) — they are a side effect of `stock.move` validation,
inventory-adjustment application, and scrap confirmation (all in `contracts/stock-transfers.md`,
`stock-inventory.md`, `stock-scrap.md`). This contract covers configuration and the read-only
valuation report, both `Inventory Manager`-only (FR-082).

**Important**: `costing_method` and the three `property_stock_*_account_id` columns are added to
`product_category` by raw `ALTER TABLE` (D1) and are **not** registered in `ProductCategory._fields`
— exactly like `account`'s own `property_account_receivable_id` on `res_partner`, which the codebase
today only ever reads via raw SQL, never through `ResPartner.write()`. A plain
`product.category.write({costing_method: ...})` would therefore silently no-op (`BaseModel.write`
filters `vals` down to `k in cls._fields`). Configuring these columns MUST go through the dedicated
REST action below, which issues a parameterised raw `UPDATE product_category SET ... WHERE id = :id`
— the same pattern this feature already uses for `product_product.tracking` (`stock`'s
`set_tracking`, `contracts/stock-traceability.md`).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `stock.valuation.layer` | `read` / `search_read` | standard | — | read-only; `Inventory Manager` only |

## REST routes

### `POST /stock_account/category/{category_id}/configure`

Body: `CategoryValuationConfig`. Raw `UPDATE product_category SET costing_method = :cm,
property_stock_valuation_account_id = :v, property_stock_input_account_id = :i,
property_stock_output_account_id = :o WHERE id = :id` (all four together — partial updates are
rejected so a category is never left with one account set and others null). `costing_method` changes
apply prospectively only (FR-079). Returns `{category_id, costing_method, property_stock_valuation_account_id,
property_stock_input_account_id, property_stock_output_account_id}`.

### `GET /stock_account/category/{category_id}/configure`

Reads the four extension columns back via raw `SELECT` (they are otherwise invisible to
`product.category.read`, which only returns `cls._all_field_names()`).

### `GET /stock/valuation/report?company_id=&category_id=&product_id=`

Returns current stock value by product/category/location as the sum of remaining
(unconsumed) valuation layers (FR-077):
`{rows: [{product_id, category_id, quantity_on_hand, value}], total_value}`.

### `GET /stock/valuation/reconcile?company_id=&category_id=`

Compares the report's total per category against `AccountAccount.get_balance` for that category's
`property_stock_valuation_account_id` (FR-078): `{category_id, report_value, ledger_net, matches:
bool}`.

## Validation models (`stock_account/validators.py`)

```text
class CategoryValuationConfig(Payload):
    costing_method: Literal["standard", "average", "fifo"] = "standard"
    property_stock_valuation_account_id: int
    property_stock_input_account_id: int
    property_stock_output_account_id: int
```
