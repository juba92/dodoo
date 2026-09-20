/**
 * Customer list (009-customer-database, US2/US3) — search/filter over
 * customers (`customer_rank > 0`), modelled on `coa-list.js`: fetch once via
 * `GET /account/customers` (not the generic `search_read` — `customer_rank`
 * isn't a declared field, ADR-046), client-side substring filter on
 * name/VAT, New button, archived toggle. The balance column is fetched from
 * the AR-ledger endpoint per visible row (US3, ADR-047).
 */
import * as api from '/web/static/api.js';
import { App } from '/web/static/app.js';
import { t, formatCurrency } from '/web/static/i18n.js';

function _debounce(fn, ms) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}

export async function render(container, _params) {
  container.innerHTML = '';

  let all = [];
  let search = '';
  let showArchived = false;

  // ── Control panel: New + search + archived toggle ─────────────────────────
  const cp = document.getElementById('control-panel');
  const searchInput = document.createElement('input');
  searchInput.type = 'search';
  searchInput.className = 'search-input';
  searchInput.placeholder = t('Search {name}…', { name: t('Customers') });
  searchInput.setAttribute('aria-label', t('Search {name}…', { name: t('Customers') }));
  searchInput.addEventListener('input', _debounce(() => { search = searchInput.value.trim().toLowerCase(); _paint(); }, 250));

  if (cp) {
    cp.innerHTML = '';
    const newBtn = document.createElement('button');
    newBtn.className = 'btn btn-primary';
    newBtn.textContent = t('New');
    newBtn.onclick = () => App.navigate('#/accounting/customer/new');
    cp.appendChild(newBtn);

    const spacer = document.createElement('div');
    spacer.className = 'o-cp-spacer';
    cp.appendChild(spacer);

    const archLabel = document.createElement('label');
    archLabel.className = 'coa-toggle';
    const archCb = document.createElement('input');
    archCb.type = 'checkbox';
    archCb.checked = showArchived;
    archCb.onchange = () => { showArchived = archCb.checked; _load(); };
    archLabel.append(archCb, document.createTextNode(' ' + t('Show Archived')));
    cp.appendChild(archLabel);

    cp.appendChild(searchInput);
  }

  // ── Table shell ───────────────────────────────────────────────────────────
  const wrap = document.createElement('div');
  wrap.style.overflowX = 'auto';
  const table = document.createElement('table');
  table.className = 'data-table';
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  [t('Name'), t('Tax/VAT Number'), t('Outstanding Balance')].forEach(txt => {
    const th = document.createElement('th');
    th.textContent = txt;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  // ── Data ──────────────────────────────────────────────────────────────────
  async function _load() {
    tbody.innerHTML = '';
    const loading = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 3;
    td.className = 'loading';
    td.textContent = t('Loading…');
    loading.appendChild(td);
    tbody.appendChild(loading);

    try {
      const qs = showArchived ? '?include_archived=true' : '';
      all = await api.get(`/account/customers${qs}`);
    } catch (err) {
      tbody.innerHTML = '';
      const er = document.createElement('tr');
      const etd = document.createElement('td');
      etd.colSpan = 3;
      etd.className = 'alert-error';
      etd.textContent = t('Error') + ': ' + err.message;
      er.appendChild(etd);
      tbody.appendChild(er);
      return;
    }
    _paint();
  }

  function _visible() {
    return all.filter(c => {
      if (!search) return true;
      return (c.name || '').toLowerCase().includes(search)
        || (c.vat || '').toLowerCase().includes(search);
    });
  }

  function _row(c) {
    const tr = document.createElement('tr');
    if (!c.active) tr.classList.add('coa-archived');
    const open = () => App.navigate('#/accounting/customer/' + c.id);
    tr.onclick = open;
    // A row is the only way to open a customer — it must be reachable and
    // operable from the keyboard, not just a pointer (ACC-002), matching
    // web/static/views/list.js's tested pattern.
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });

    const nameTd = document.createElement('td');
    nameTd.textContent = c.name || '';
    if (!c.active) {
      const badge = document.createElement('span');
      badge.className = 'badge badge-cancel coa-arch-badge';
      badge.textContent = t('Archived');
      nameTd.appendChild(document.createTextNode(' '));
      nameTd.appendChild(badge);
    }
    tr.appendChild(nameTd);

    const vatTd = document.createElement('td');
    vatTd.textContent = c.vat || '';
    tr.appendChild(vatTd);

    const balTd = document.createElement('td');
    balTd.textContent = '…';
    tr.appendChild(balTd);
    api.get(`/account/partner/${c.id}/ar-ledger`)
      .then(ledger => { balTd.textContent = formatCurrency(parseFloat(ledger.balance || 0)); })
      .catch(() => { balTd.textContent = '—'; });

    return tr;
  }

  function _paint() {
    tbody.innerHTML = '';
    const rows = _visible();
    if (!rows.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 3;
      td.textContent = t('No customers found.');
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    rows.forEach(c => tbody.appendChild(_row(c)));
  }

  await _load();
}
