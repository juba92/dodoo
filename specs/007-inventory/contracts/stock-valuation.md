# Contract: Inventory Valuation & Accounting Integration (US8)

Lives in `dodoo/addons/stock_account/`. Valuation layers and journal entries are never created via
a direct user-facing mutation endpoint (FR-084) — they are a side effect of `stock.move` validation,
inventory-adjustment application, and scrap confirmation (all in `contracts/stock-transfers.md`,
`stock-inventory.md`, `stock-scrap.md`). This contract covers configuration (read/write on
`product.category`'s costing fields) and the read-only valuation report, both `Inventory Manager`-only
(FR-082).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `product.category` | `write` | `{costing_method: "standard"\|"average"\|"fifo"}` | `True` | prospective only (FR-079) |
| `product.category` | `write` | `{property_stock_valuation_account_id, property_stock_input_account_id, property_stock_output_account_id}` | `True` | the three `ALTER TABLE`-added columns (D1); still ordinary `write` calls once the columns exist |
| `stock.valuation.layer` | `read` / `search_read` | standard | — | read-only; `Inventory Manager` only |

## REST routes

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
class CostingMethodUpdate(Payload):
    costing_method: Literal["standard", "average", "fifo"]

class CategoryAccountsUpdate(Payload):
    property_stock_valuation_account_id: int
    property_stock_input_account_id: int
    property_stock_output_account_id: int
```
