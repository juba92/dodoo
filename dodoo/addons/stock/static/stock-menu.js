// Inventory application menus (feature 007). Same shape as HR_MENU/ACCOUNTING_MENU.
// `requires` gates the section client-side against /web/core/info (stock_groups);
// the real enforcement is the ir.rule record rules + REST action group checks.
export const STOCK_MENU = [
  {
    section: 'Products', requires: null,
    items: [
      { label: 'Products',          hash: '#/inventory/model/product.template' },
      { label: 'Product Variants',  hash: '#/inventory/model/product.product' },
      { label: 'Product Categories', hash: '#/inventory/model/product.category' },
      { label: 'Units of Measure',  hash: '#/inventory/model/uom.uom' },
    ],
  },
  {
    section: 'Warehouses', requires: 'manager',
    items: [
      { label: 'Warehouses',      hash: '#/inventory/model/stock.warehouse' },
      { label: 'Locations',       hash: '#/inventory/model/stock.location' },
      { label: 'Operation Types', hash: '#/inventory/model/stock.picking.type' },
    ],
  },
  {
    // TODO(follow-up): a bespoke transfer-kanban.js grouped by operation-type/state
    // (FR-033) is not yet built; the generic list/form views cover create/confirm/
    // validate/cancel/return via JSON-RPC + the REST workflow actions in the interim.
    section: 'Transfers', requires: null,
    items: [
      { label: 'Transfers', hash: '#/inventory/model/stock.picking' },
      { label: 'Stock Moves', hash: '#/inventory/model/stock.move' },
    ],
  },
  {
    // TODO(follow-up): a bespoke count-sheet view (editable counted_quantity + apply
    // action, FR-037) is not yet built; stock.quant is browsable/editable generically.
    section: 'Physical Inventory', requires: null,
    items: [
      { label: 'On-Hand Quantities', hash: '#/inventory/model/stock.quant' },
      { label: 'Adjustment History', hash: '#/inventory/model/stock.inventory.adjustment.log' },
    ],
  },
  {
    section: 'Traceability', requires: null,
    items: [
      { label: 'Lots & Serial Numbers', hash: '#/inventory/model/stock.lot' },
      { label: 'Packages',              hash: '#/inventory/model/stock.quant.package' },
    ],
  },
  {
    section: 'Configuration', requires: 'manager',
    items: [
      { label: 'Putaway Rules',     hash: '#/inventory/model/stock.putaway.rule' },
      { label: 'Storage Categories', hash: '#/inventory/model/stock.storage.category' },
      { label: 'Routes',            hash: '#/inventory/model/stock.route' },
      { label: 'Reordering Rules',  hash: '#/inventory/model/stock.warehouse.orderpoint' },
    ],
  },
  {
    section: 'Scrap', requires: null,
    items: [
      { label: 'Scrap', hash: '#/inventory/model/stock.scrap' },
    ],
  },
  {
    // TODO(follow-up): a bespoke valuation-report page is not yet built; the
    // GET /stock/valuation/report and /reconcile REST endpoints exist and are
    // covered by tests, awaiting a UI.
    section: 'Reporting', requires: 'manager',
    items: [
      { label: 'Valuation Layers', hash: '#/inventory/model/stock.valuation.layer' },
    ],
  },
];
