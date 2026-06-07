import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';

const ROUTE_CONFIG = {
  'invoices':            { model: 'account.move',    domain: [['move_type', '=', 'out_invoice']], label: 'Customer Invoices',      newType: 'out_invoice' },
  'credit-notes':        { model: 'account.move',    domain: [['move_type', '=', 'out_refund']],  label: 'Customer Credit Notes',  newType: 'out_refund' },
  'customer-payments':   { model: 'account.payment', domain: [['payment_type', '=', 'inbound']],  label: 'Customer Payments' },
  'bills':               { model: 'account.move',    domain: [['move_type', '=', 'in_invoice']],  label: 'Vendor Bills',           newType: 'in_invoice' },
  'vendor-credit-notes': { model: 'account.move',    domain: [['move_type', '=', 'in_refund']],   label: 'Vendor Credit Notes',   newType: 'in_refund' },
  'vendor-payments':     { model: 'account.payment', domain: [['payment_type', '=', 'outbound']], label: 'Vendor Payments' },
  'journal-entries':     { model: 'account.move',    domain: [['move_type', '=', 'entry']],       label: 'Journal Entries',        newType: 'entry' },
  'chart-of-accounts':   { model: 'account.account', domain: [['active', '=', true]],             label: 'Chart of Accounts' },
  'journals':            { model: 'account.journal', domain: [],                                   label: 'Journals' },
};

function _fmt(amount) {
  if (amount === null || amount === undefined) return '—';
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parseFloat(amount));
}

function _date(d) { return d ? d.substring(0, 10) : '—'; }

function _badge(state, paymentState) {
  if (state === 'draft')  return { label: 'Draft',      cls: 'badge-draft' };
  if (state === 'cancel') return { label: 'Cancelled',  cls: 'badge-cancel' };
  if (paymentState === 'paid')     return { label: 'Paid',     cls: 'badge-paid' };
  if (paymentState === 'reversed') return { label: 'Reversed', cls: 'badge-cancel' };
  if (paymentState === 'partial')  return { label: 'Partial',  cls: 'badge-partial' };
  return { label: 'Confirmed', cls: 'badge-posted' };
}

function _columns(model) {
  if (model === 'account.move') return [
    { field: 'name',             label: 'Number',        render: v => (v && v !== '/') ? v : '—' },
    { field: 'partner_id',       label: 'Partner',       render: v => Array.isArray(v) ? v[1] : '—' },
    { field: 'invoice_date',     label: 'Invoice Date',  render: _date },
    { field: 'invoice_date_due', label: 'Due Date',      render: _date },
    { field: 'amount_total',     label: 'Total',         render: _fmt, right: true },
    { field: '__status',         label: 'Status',        isStatus: true },
  ];
  if (model === 'account.payment') return [
    { field: 'name',       label: 'Number',  render: v => (v && v !== '/') ? v : '—' },
    { field: 'partner_id', label: 'Partner', render: v => Array.isArray(v) ? v[1] : '—' },
    { field: 'date',       label: 'Date',    render: _date },
    { field: 'amount',     label: 'Amount',  render: _fmt, right: true },
    { field: 'state',      label: 'Status',  render: v => v ?? '—' },
  ];
  if (model === 'account.account') return [
    { field: 'code',         label: 'Code',          render: v => v ?? '—' },
    { field: 'name',         label: 'Name',          render: v => v ?? '—' },
    { field: 'account_type', label: 'Type',          render: v => v ?? '—' },
    { field: 'reconcile',    label: 'Reconcilable',  render: v => v ? 'Yes' : 'No' },
  ];
  if (model === 'account.journal') return [
    { field: 'name', label: 'Name', render: v => v ?? '—' },
    { field: 'code', label: 'Code', render: v => v ?? '—' },
    { field: 'type', label: 'Type', render: v => v ?? '—' },
  ];
  return [];
}

function _debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export async function render(container, params) {
  const config = ROUTE_CONFIG[params.route];
  if (!config) { container.textContent = `Unknown view: ${params.route}`; return; }

  const { model, domain, label, newType } = config;
  const cols = _columns(model);
  let searchTerm = '';
  let offset = 0;
  const LIMIT = 80;

  // Control panel
  const cp = document.getElementById('control-panel');
  if (cp) {
    cp.innerHTML = '';
    if (newType) {
      const newBtn = document.createElement('button');
      newBtn.className = 'btn btn-primary';
      newBtn.textContent = 'New';
      newBtn.onclick = () => App.navigate(`#/accounting/move/new?type=${newType}`);
      cp.appendChild(newBtn);
    }
    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'search-input';
    search.placeholder = `Search ${label}…`;
    search.addEventListener('input', _debounce(() => { searchTerm = search.value.trim(); offset = 0; fetchAndRender(); }, 400));
    cp.appendChild(search);
  }

  container.innerHTML = '';

  // Table
  const wrapper = document.createElement('div');
  wrapper.style.overflowX = 'auto';
  container.appendChild(wrapper);

  const table = document.createElement('table');
  table.className = 'data-table';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  cols.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col.label;
    if (col.right) th.className = 'text-right';
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  wrapper.appendChild(table);

  const pagination = document.createElement('div');
  pagination.className = 'pagination';
  container.appendChild(pagination);

  async function fetchAndRender() {
    tbody.innerHTML = '';
    pagination.innerHTML = '';

    const loadRow = document.createElement('tr');
    const loadTd = document.createElement('td');
    loadTd.colSpan = cols.length;
    loadTd.className = 'loading';
    loadTd.textContent = 'Loading…';
    loadRow.appendChild(loadTd);
    tbody.appendChild(loadRow);

    try {
      const searchDomain = searchTerm
        ? [...domain, ['name', 'ilike', searchTerm]]
        : domain;

      const fields = ['id', 'state', 'payment_state',
        ...cols.filter(c => !c.isStatus).map(c => c.field)];

      const records = await api.rpc(model, 'search_read', [searchDomain], {
        fields: [...new Set(fields)],
        limit: LIMIT,
        offset,
        order: 'id desc',
      });

      tbody.innerHTML = '';
      if (records.length === 0) {
        const emptyRow = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = cols.length;
        td.className = 'empty-state';
        td.textContent = `No ${label.toLowerCase()} found.`;
        emptyRow.appendChild(td);
        tbody.appendChild(emptyRow);
      } else {
        records.forEach(rec => {
          const tr = document.createElement('tr');
          tr.onclick = () => {
            if (model === 'account.move') App.navigate(`#/accounting/move/${rec.id}`);
            else App.navigate(`#/accounting/model/${model}/${rec.id}`);
          };
          cols.forEach(col => {
            const td = document.createElement('td');
            if (col.isStatus) {
              const b = _badge(rec.state, rec.payment_state);
              const span = document.createElement('span');
              span.className = `badge ${b.cls}`;
              span.textContent = b.label;
              td.appendChild(span);
            } else {
              td.textContent = col.render ? col.render(rec[col.field]) : (rec[col.field] ?? '—');
              if (col.right) td.className = 'text-right';
            }
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
      }

      // Pagination
      const info = document.createElement('span');
      info.style.flex = '1';
      info.textContent = records.length > 0 ? `${offset + 1}–${offset + records.length}` : '0';
      pagination.appendChild(info);
      if (offset > 0) {
        const prev = document.createElement('button');
        prev.className = 'btn btn-secondary';
        prev.textContent = '← Prev';
        prev.onclick = () => { offset = Math.max(0, offset - LIMIT); fetchAndRender(); };
        pagination.appendChild(prev);
      }
      if (records.length === LIMIT) {
        const next = document.createElement('button');
        next.className = 'btn btn-secondary';
        next.textContent = 'Next →';
        next.onclick = () => { offset += LIMIT; fetchAndRender(); };
        pagination.appendChild(next);
      }
    } catch (err) {
      tbody.innerHTML = '';
      const errRow = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = cols.length;
      td.className = 'alert-error';
      td.textContent = 'Error: ' + err.message;
      errRow.appendChild(td);
      tbody.appendChild(errRow);
    }
  }

  await fetchAndRender();
}
