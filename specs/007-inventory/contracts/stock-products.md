# Contract: Product Catalog, Variants & Units of Measure (US1)

Two transports, as in every prior feature: JSON-RPC `execute_kw` (generic CRUD on any
`BaseModel`, e.g. `product.category`, `uom.uom`, `product.template`, `product.product`) for
plain create/read/write/unlink/search, and REST `@route` actions (`dodoo.http.routing.route`,
`auth="session"`) for verbs that aren't plain CRUD. Every REST body is parsed through a
`Payload` (Pydantic v2, `extra="forbid"`) subclass in `dodoo/addons/product/validators.py` before
any processing (SEC-001); every mutation additionally requires an authenticated session
(`auth="session"`) — the product catalog itself carries no dedicated security group (readable by
any authenticated user, write access gated by `Inventory Manager` per `contracts/security-groups.md`).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `product.category` | `create` / `read` / `write` / `unlink` / `search_read` | standard `BaseModel` CRUD | — | `company_id` nullable (FR-001) |
| `uom.category` / `uom.uom` | `create` / `read` / `write` / `search_read` | standard | — | FR-002 |
| `product.template` | `create` / `read` / `write` / `search_read` | standard | — | FR-004 |
| `product.attribute` / `product.attribute.value` | `create` / `read` / `search_read` | standard | — | FR-005 |
| `product.template.attribute.line` | `create` / `write` | `{template_id, attribute_id, value_ids}` | line id | triggers variant regeneration, see REST below |
| `product.product` | `read` / `write` / `search_read` | standard | — | `write` on `barcode`/`price_extra` only (FR-007); other fields are template-inherited and read-only on the variant |

## REST routes

### `POST /product/template/{template_id}/attribute-lines/apply`

Regenerates variants (FR-006) after attribute lines change. Body: `ApplyAttributeLines` (list of
`{attribute_id, value_ids}`). Replaces the template's attribute lines, then generates one
`product.product` per new combination in the Cartesian product, leaving existing variants for
unchanged combinations untouched. Returns `{template_id, variant_ids: [...]}`.

### `GET /product/search?q=&category_id=&product_type=&tracked_only=`

Full-text/barcode search across templates and variants (FR-009). Returns
`{results: [{product_id, template_id, name, barcode, category_id, product_type, is_storable}]}`.

### `GET /product/{product_id}/uom-convert?qty=&to_uom_id=`

Converts `qty` (in the product's `uom_id`) to `to_uom_id`; `400` if `to_uom_id` is not in the same
`uom.category` (FR-003).

## Validation models (`product/validators.py`)

```text
class ApplyAttributeLines(Payload):
    lines: list[AttributeLineSpec]   # AttributeLineSpec = {attribute_id: int, value_ids: list[int]}

class ProductCategoryCreate(Payload):
    name: str; parent_id: int | None; company_id: int | None; costing_method: Literal["standard","average","fifo"] = "standard"

class UomCreate(Payload):
    name: str; category_id: int; uom_type: Literal["reference","bigger","smaller"]; ratio: float = Field(gt=0)

class ProductTemplateCreate(Payload):
    name: str; category_id: int | None; product_type: Literal["goods","service"] = "goods"
    is_storable: bool = False; uom_id: int; purchase_uom_id: int | None
    list_price: Decimal = Decimal("0"); standard_price: Decimal = Decimal("0")
    barcode: str | None; company_id: int | None
```
