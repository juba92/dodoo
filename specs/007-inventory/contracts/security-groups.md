# Contract: Security Groups & Record Rules (cross-cutting)

## Groups (`dodoo/addons/stock/security.py`)

| Name | Level | Notes |
|---|---|---|
| `Inventory User` | base | create/validate transfers, counts, lots/serials, packages, scrap (FR-081) |
| `Inventory Manager` | superset of User | + warehouses, locations, operation types, putaway, storage categories, routes, reordering, costing config (FR-082) |

`assign_inventory_group(env, uid, level: Literal["user","manager"])` mirrors
`hr.security.assign_hr_group` — granting `manager` also grants `user` (ancestor-chain materialisation
at assignment time, since `res.groups` has no implied-group graph).

## Record rules (`dodoo/addons/stock/data/rules.py`)

| Rule | Models | Domain | Groups | Perms |
|---|---|---|---|---|
| `manager_full` | `stock.warehouse`, `stock.location`, `stock.picking.type`, `stock.putaway.rule`, `stock.storage.category`, `stock.route`, `stock.rule`, `stock.warehouse.orderpoint` | `[["company_id","in","$company_ids"]]` | `Inventory Manager` | `rwck` |
| `user_or_manager_operate` | `stock.picking`, `stock.move`, `stock.move.line`, `stock.quant`, `stock.lot`, `stock.quant.package`, `stock.scrap` | company-scoped via warehouse/location join | `Inventory User`, `Inventory Manager` | `rwck` |
| `catalog_read` | `product.category`, `uom.category`, `uom.uom`, `product.template`, `product.product` | `["\|", ["company_id","=",None], ["company_id","in","$company_ids"]]` | any authenticated user | `r` |
| `catalog_admin_write` | same catalog models | `[[1,"=",1]]` | `Inventory Manager` | `wck` |
| `valuation_manager_read` | `stock.valuation.layer` | `[["company_id","in","$company_ids"]]` | `Inventory Manager` | `r` |

## `/web/core/info` extension (`dodoo/addons/base/http/__init__.py`)

```text
stock_groups = sorted(n for n in held if n.startswith("Inventory "))
# ... included in the JSONResponse dict alongside hr_groups / fleet_manager
```

Consumed by `web/static/app.js`'s `_stockHas(requires)` / `_renderStockMenu(sidebar, currentHash)`,
added following the existing `_hrHas`/`_renderHrMenu` pair exactly, dispatched from `_renderSidebar`
on `hash.startsWith('#/inventory')`.
